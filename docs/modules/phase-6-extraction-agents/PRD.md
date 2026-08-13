# PRD: Extraction Agents (Pydantic AI)
Phase: 6
Module codes: B8 (`extraction`) from plan.md §6, plus the shared `app/services/llm/`
provider layer every later LLM-calling phase depends on.

## Problem

A postmortem's indexed chunks (Phase 5) are searchable text, but nothing yet turns
that text into the structured knowledge Hindsight's whole value proposition depends
on: what actually triggered the incident, what the root cause was, what services were
involved and how, and what recurring failure pattern it represents. Retrieval (Phase
7), correlation, and brief generation (Phase 8-9) all need this structured layer —
`postmortem_facts`, `postmortem_services`, `postmortem_failure_modes` — populated
before they can do anything useful. This phase also builds the shared LLM abstraction
(`app/services/llm/`) every later phase that calls a model reuses, so provider
selection, fallback, and graceful degradation are solved once, not per-phase.

## Actors

- The background worker, running extraction as a queue job after a postmortem is
  successfully indexed.
- Every later backend module that reads `postmortem_facts`/`postmortem_services`/
  `postmortem_failure_modes` (retrieval's graph expansion, the correlator, brief
  generation) — this phase is what populates those tables.
- Every later module that calls an LLM (the analyst node in Phase 8) — this phase's
  `LLMProvider`/`LLMRouter` is the interface they call through, not a per-phase
  reimplementation.
- Santhosh, running with no LLM key configured for most of this build (per plan.md
  §10's "no key at all" degradation level) — extraction must fail *cleanly* and
  *visibly* in that case, not crash the worker or silently produce nothing without a
  trace.

## Functional Requirements

FR-01: `app/services/llm/provider.py` defines an `LLMProvider` Protocol with
`complete(prompt, *, system) -> LLMResponse` (raw text plus token counts) and
`structured(prompt, *, system, result_type: type[T]) -> T` (typed output via
pydantic-ai). `gemini.py`, `groq.py`, `ollama.py` each implement it against the
actually-installed `pydantic-ai` 2.29.0 API (`output_type`/`.output`, not the
plan's originally-assumed `result_type`/`.data` — see Phase 0's ADR).

FR-02: `app/services/llm/router.py` tries providers in priority order (Gemini →
Groq → Ollama, matching plan.md §10's degradation ladder), retrying transient
failures within a provider via `tenacity` before falling through to the next one. If
every configured provider fails, it raises the existing `LLMUnavailableError`
(`app/core/errors.py`) rather than returning a degraded/partial result — callers are
responsible for handling that exception by degrading, per that error class's existing
contract.

FR-03: `app/services/llm/cache.py` implements a semantic + exact-hash cache backed by
the existing `semantic_cache` table: an exact SHA-256 hash match on the prompt is
checked first (cheap path); if none, a cosine-similarity search over the prompt's
embedding within the same `workspace_id`+`purpose` is tried above a configurable
threshold. A cache hit increments `hits`. This phase builds and unit-tests the module
standalone — it is not yet wired into the extraction agents' call path (see Out of
Scope).

FR-04: `facts_agent.py` extracts `ExtractedFacts` — five lists (`triggers`,
`root_causes`, `remediations`, `detection_gaps`, `contributing_factors`), matching
`FactType`'s five existing values — each item citing the `chunk_id` it was drawn
from. Any fact citing a `chunk_id` that isn't among the postmortem's actual chunks is
dropped before persisting — a deterministic post-processing guard, not something left
to the model's discretion.

FR-05: `failure_mode_agent.py` classifies a postmortem against a fixed 12-family
taxonomy plus `other` (defined in `app/services/extraction/taxonomy.py`, since no
concrete list exists in plan.md/Master-Prompt.md beyond "12 recurring failure-mode
families" — this phase defines it). A postmortem can match more than one family
(the `postmortem_failure_modes` join table already supports many-to-many), each with
its own confidence.

FR-06: `service_linker_agent.py` links a postmortem to services **by name**, with a
role (`root_cause`/`affected`/`downstream`) matching `ServiceLinkRole`'s existing
values. Every returned name is resolved against the workspace's actual service
catalog (Phase 4); a name that doesn't match any real service is dropped rather than
inventing a new one.

FR-07: All three agents run inside one `extract_postmortem` job, chained
automatically by `ingest_postmortem`'s handler once a postmortem reaches `indexed` —
not three separate job rows racing independent retry timelines for what is
conceptually one unit of work.

FR-08: Every prompt sent to an extraction agent delimits the postmortem's chunk text
explicitly and states that it is untrusted, model-facing data — not instructions —
regardless of `injection_flagged`. This applies even to a flagged postmortem: ingestion
never blocks on the flag (Phase 5), and extraction must not either, but the prompt-level
guardrail is what keeps injected content from being followed as instructions instead of
read as data.

FR-09: If no LLM provider is configured or reachable, the `extract_postmortem` job
fails with a clear `LLMUnavailableError`-derived message in `jobs.last_error`,
retries with the same backoff every other job kind gets, and eventually dead-letters —
it does not hang, crash the worker, or silently mark the postmortem as successfully
extracted with zero facts.

## User Stories

- As the author of Phase 7 (retrieval) or Phase 8 (briefs), I want
  `postmortem_facts`/`postmortem_services`/`postmortem_failure_modes` reliably
  populated after ingestion, with every fact traceable to a real chunk, so I never
  have to re-verify extraction's output before building on it.
- As Santhosh running this project with no LLM key most of the time, I want
  extraction's failure to be honest and inspectable (`jobs.last_error`), not a silent
  no-op or a crashed worker — so adding a key later and re-running is straightforward.
- As the author of a later LLM-calling phase, I want one shared provider/router
  abstraction with fallback already solved, so I'm not re-implementing "try Gemini,
  fall back to Groq" from scratch.

## Out of Scope

- Wiring the semantic cache into the extraction agents' actual call path — built and
  tested this phase, but its first real consumer is Phase 8's brief generation
  (plan.md §10's explicit "cached briefs for seeded incidents" degradation level),
  where returning a cached response for a near-duplicate *incident* is the intended
  cost-saving behavior. Caching per-postmortem fact extraction risks a near-duplicate
  prompt returning another postmortem's facts, which this phase avoids by not doing it.
- The LangGraph agent pipeline (normalizer/retriever/correlator/analyst/critic) —
  Phase 8. This phase's agents are plain pydantic-ai agents run from a queue job, not
  LangGraph nodes.
- Live verification against a real Gemini/Groq/Ollama endpoint — no LLM key is
  configured for this build session (see the module's NFR/Testability section); all
  agent behavior is verified against `pydantic-ai`'s `TestModel`/`FunctionModel`
  offline testing utilities, which exercise the exact same `Agent`/`output_type`
  code path a real model would. Santhosh will add a real key and verify live
  end-to-end generation himself before this phase's work is treated as fully proven
  against a real provider.

## Acceptance Criteria

1. Ingest a postmortem (with a mocked/test LLM configured): its job chain reaches
   `extract_postmortem` after `ingest_postmortem`, and `postmortem_facts`,
   `postmortem_services`, and `postmortem_failure_modes` rows exist afterward.
2. A fact whose `chunk_id` doesn't belong to the postmortem's actual chunk set is
   never persisted, even if the (test) model returns one.
3. A service name the (test) model returns that doesn't exist in the workspace's
   catalog is dropped, never invented as a new service.
4. A deliberately injected instruction inside a test postmortem's text does not
   change extraction's behavior (verified via a `FunctionModel` that would reveal if
   the "prompt" it received treated the injected text as an instruction rather than
   delimited data).
5. With no LLM provider configured at all, the extraction job fails cleanly with a
   readable `last_error`, retries with backoff, and dead-letters — the worker process
   itself never crashes and the postmortem's own ingestion status is unaffected.
6. `ruff`, `mypy --strict`, and `pytest` are all clean.
