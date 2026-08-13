# ADR 0006: Extraction Agents — LLM Layer Design and Bugs Found

## 1. The failure-mode taxonomy is this phase's own design decision

**Context.** Master-Prompt.md's Phase 6 spec calls for classifying postmortems against
"the fixed 12-family taxonomy plus other" and plan.md references "12 recurring
failure-mode families" in its seed-corpus description — neither document names the
actual 12 families anywhere.

**Decision.** `app/services/extraction/taxonomy.py` defines
`CONFIGURATION_ERROR`, `DEPLOYMENT_FAILURE`, `CAPACITY_EXHAUSTION`,
`DEPENDENCY_FAILURE`, `NETWORK_CONNECTIVITY`, `DATA_CORRUPTION`, `CODE_DEFECT`,
`HUMAN_PROCESS_ERROR`, `SECURITY_INCIDENT`, `INFRASTRUCTURE_HARDWARE`,
`SCALING_LOAD`, `MONITORING_GAP`, plus `OTHER` — a standard SRE incident-taxonomy
shape (deployment/config/capacity/dependency/network/data/code/process/security/
hardware/scale/detection), chosen so Phase 11's seed corpus (80 postmortems across
these families) has a real, joinable classification space to generate against, and so
the correlator's later failure-mode-overlap scoring (Phase 8) has fixed categories to
compare rather than free-form strings. `postmortem_failure_modes` is a many-to-many
join table, so a postmortem can legitimately match more than one family — the agent's
output is a list of classifications, not a single pick.

## 2. `LLMProvider`/`LLMRouter`/`cache.py` — one shared abstraction for every future LLM call

**Context.** plan.md §10 specifies a three-level fallback (Gemini free → Groq free →
Ollama local) and three degradation levels depending on what's actually configured.
Every later phase that calls an LLM (Phase 8's analyst node, specifically) needs this
same fallback behavior — building it once here, generically, avoids every later phase
reimplementing "try the primary, fall back on failure."

**Decision.** `LLMProvider` is a Protocol (`complete`/`structured`), so
`GeminiProvider`/`GroqLLMProvider`/`OllamaLLMProvider` are structurally interchangeable
without a shared base class. Each builds its underlying pydantic-ai `Model` lazily (on
first actual call, not at construction) so a provider whose key is empty or whose
package isn't installed never crashes anything by merely existing in the router's list.
`LLMRouter` tries providers in order, retrying transient failures within one provider
via `tenacity.AsyncRetrying` before moving to the next; if every provider fails, it
raises the existing `LLMUnavailableError` (already defined in `app/core/errors.py`
since Phase 1, unused until now) rather than returning a degraded value — callers
handle degradation explicitly, matching that error class's documented contract.
`build_router(settings)` always appends `OllamaLLMProvider` last regardless of whether
any key is configured, since it's plan.md's documented zero-key fallback, not an
optional extra — in this build's actual configuration (no Gemini/Groq key, no local
Ollama server), the provider list is just `[Ollama]`, and its connection failure is
what naturally produces `LLMUnavailableError` through the router's ordinary
"every provider failed" path, with no separate "zero providers configured"
special case needed.

`app/services/llm/cache.py` (exact-hash-then-semantic-cosine, scoped by
`workspace_id`+`purpose`) is built and unit-tested this phase but **not** wired into
the extraction agents' call path — caching per-postmortem fact extraction risks a
near-duplicate *prompt* returning a completely different postmortem's facts, which
this phase deliberately avoids. Its first real consumer is Phase 8's brief generation,
where plan.md §10 explicitly names "cached briefs for seeded incidents" as an
intentional degradation behavior — a near-duplicate *incident* legitimately reusing a
cached brief is the actual intended use case for this cache, not per-document
extraction.

## 3. `.env`/`.env.example`'s inline comments were silently becoming literal config values

**Context.** This is the first phase that ever actually *reads*
`Settings.llm_api_key`/`llm_model`/`groq_api_key` in a real code path — Phases 1-5
declared these fields but never consumed them. Live-testing `build_router` against
this repo's real `.env` produced bizarre failures: Gemini was attempted with a "model
name" of literally `"# CHECK current free-tier model ID at the provider"`, and Groq
returned `401 Invalid API Key` using a key that was actually the literal string
`"# fallback when Gemini quota exhausted"`.

**Decision.** `.env`/`.env.example` had lines shaped like
`LLM_API_KEY=                         # Gemini: free key at aistudio.google.com`
— an inline comment trailing a *blank* value. `python-dotenv` (which
`pydantic-settings` uses for `env_file` loading) correctly strips a trailing `#`
comment when there's real content before it (confirmed: `LLM_PROVIDER=gemini
# gemini | groq | ollama` parses to the clean string `"gemini"`), but does **not**
strip it when the value portion is empty — in that case the entire remainder of the
line, comment included, becomes the literal field value. Fixed by moving every such
comment to its own line above the `KEY=` line in both `.env.example` (committed
template) and the local `.env` (gitignored, fixed directly) — never put an inline
comment on a line whose value is meant to be blank. This bug would have hit **every**
future clone that copies `.env.example` as instructed and leaves the LLM keys blank
(the documented, expected "no key" path) — not an edge case, the default path.

## 4. Testing an LLM-calling agent without a real key: `TestModel` and `FunctionModel`

**Context.** Santhosh's explicit choice this phase: build and verify extraction
against mocks, add a real Gemini/Groq key and verify live generation himself later
(see the PRD's Out of Scope). The risk with mocking an LLM layer is producing tests
that only prove "the code runs," not "the code sends what it's supposed to send."

**Decision.** Router-level tests (`test_llm_router.py`) use plain fake `LLMProvider`
implementations — no pydantic-ai involved, since routing/fallback logic doesn't touch
model internals. Agent-level tests (`test_extraction.py`, `test_extraction_service.py`)
wrap `pydantic-ai`'s real `TestModel`/`FunctionModel` in a small `FakeModelProvider`
test double (`tests/conftest.py`) that constructs a real `pydantic_ai.Agent(model,
output_type=...)` — the exact code path a real Gemini call would take — just swapping
which `Model` backs it. `TestModel(custom_output_args=...)` gives deterministic typed
output for straightforward shape assertions; `FunctionModel` goes further, handing the
test a callback that receives the actual `ModelMessage` list the agent constructed —
used specifically to prove the injection-defense guardrail (FR-08) by asserting the
untrusted-data notice is present and an injected phrase appears only inside a
delimited `<chunk>` block in the *user* prompt, never promoted into the *system*
prompt. A `TestModel`-only test could show the pipeline "worked" even if the delimiting
had silently broken; inspecting the actual constructed prompt cannot make that mistake.

## 5. Test isolation: draining a job kind that didn't exist before this phase

**Context.** `ingest_postmortem`'s handler now auto-enqueues an `extract_postmortem`
job on success (FR-07's job-chaining requirement). Every existing test that ingests a
postmortem without caring about extraction — most of `test_postmortems.py`, and two of
`test_extraction_service.py`'s own tests that call `run_extraction` directly rather
than through the queue — left that auto-enqueued job sitting `queued` forever. Across
enough repeated local `pytest` invocations against the shared, non-truncated dev
database (the same class of environment as Phase 5's ADR 0005 §6), this accumulated
past a `claim(..., limit=50)` call's window: `claim()` orders by `created_at ASC`, so a
brand-new job loses to 50+ older orphaned ones still sitting in the queue, and a test
expecting to find its own freshly-enqueued job found nothing.

**Decision.** Both `test_postmortems.py`'s and `test_extraction_service.py`'s
ingestion helpers now drain and discard any `extract_postmortem` job that ingestion
auto-enqueues as a side effect, immediately after ingesting — neither file tests
extraction via the queue itself, so there's nothing to preserve. The one test that
does need to drive `handle_extract_postmortem` against a real, controlled job
(`test_handle_extract_postmortem_fails_cleanly_with_no_llm_configured`) enqueues its
own dedicated job explicitly rather than relying on whichever job happens to still be
queued from the auto-chain, sidestepping the ordering/limit question entirely. Same
underlying lesson as ADR 0005 §6, applied to a new job kind this phase introduced:
a background job's side effects need explicit cleanup in any test that doesn't care
about them, or they leak into whichever other test happens to query that queue next.

## 6. Verified end-to-end against the live worker container, not just pytest

**Context.** Same discipline as ADR 0005 §5 — pytest's simulated job-draining proves
the pipeline logic is correct but never exercises the real `python -m
app.workers.worker` entrypoint or a real chained multi-job sequence.

**Decision.** Rebuilt the `api`/`worker` images (both needed the new `groq` dependency
baked in, not just live-`pip install`ed into a running container), started the real
worker, and drove the full chain via `curl` against the live `api` container: posted a
postmortem, watched it reach `indexed`, watched the worker automatically claim the
chained `extract_postmortem` job, confirmed only Ollama was attempted (Gemini/Groq
correctly skipped once the `.env` bug above was fixed) via `docker compose logs
worker`, and confirmed the job failed with `"All LLM providers unavailable"` and
dead-lettered after retrying — exactly matching FR-09, verified against real
infrastructure rather than assumed from the design doc.
