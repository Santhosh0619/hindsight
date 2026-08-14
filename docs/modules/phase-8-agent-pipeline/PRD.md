# PRD: LangGraph Agent Pipeline
Phase: 8
Module codes: none frontend-facing this phase — this is the six-node pipeline that
Phase 9's F5 (New Incident) and F6 (Incident Detail) will drive and render.

## Problem

A responder pastes a raw alert. Getting from that to a trustworthy, cited brief needs
more than one LLM call — it needs structured understanding of what's actually
happening (not free text), retrieval that combines the three signals Phase 7 already
built, deterministic correlation against the service graph and failure-mode history
(the parts that don't need an LLM to be right and shouldn't have their reliability
gated by one), synthesis with hard citation requirements, and a self-check that can
catch its own bad citations and correct course — automatically, not just report a low
score and stop. This phase is where that whole loop becomes real, running, and testable
code: six nodes wired into a LangGraph `StateGraph`, checkpointed to Postgres so a brief
survives a worker restart and an incident's conversation persists across turns.

## Actors

- The LangGraph pipeline itself, invoked by Phase 9's `incidents_service.generate_brief`
  with an existing `incident_id` — this phase does not create incidents or expose an
  API; it builds the graph Phase 9 calls.
- Phase 9's SSE endpoint, which will consume `app/agents/streaming.py`'s event stream to
  drive F5's live pipeline visualization.
- The Phase 12 evaluation harness, which needs the graph's output (`IncidentBrief`,
  citation validity, correction-pass count) as its scoring input.

## Functional Requirements

FR-01: `normalizer_node` turns raw alert text into a structured `IncidentSignal` via a
Pydantic AI agent (symptoms, error strings, metrics, a time window guess, a severity
guess) and resolves any service names the model names against the real catalog —
matched names become `affected_service_ids`, unmatched names go to
`unresolved_mentions` and are never invented into a fake service id.

FR-02: `retriever_node` builds a query from the normalized signal and calls Phase 7's
`hybrid_search` in `mode="hybrid"`. On a corrective retry (retry_count > 0), it rewrites
the query using the critic's `suggested_refinements` and excludes postmortems the critic
already rejected, so a retry explores different ground rather than re-fetching the same
results.

FR-03: `correlator_node` runs with **no LLM call** — it computes blast radius from the
signal's affected services via Phase 4's `GraphStore`, and for every retrieved
postmortem produces a `CandidateMatch` carrying five independently-inspectable
subscores (`vector_score`, `keyword_score`, `graph_score`, `failure_mode_overlap`,
`recency`) plus an overall rank. Fully deterministic and unit-testable without any
model in the loop.

FR-04: `analyst_node` synthesizes `DraftBrief` (ranked hypotheses, runbook steps,
citations) via an LLM call. Every hypothesis carries at least one citation to a real
`chunk_id`. Retrieved postmortem content is fenced and explicitly labelled untrusted
data in the prompt, matching Phase 6's injection-defense pattern.

FR-05: `critic_node` verifies the draft in two stages. **Deterministic first:** every
cited `chunk_id` must exist in the retrieval set and its chunk text must plausibly
contain the claim's key terms — a citation failing either check is a hard fail
regardless of what any model says. **Then an LLM judge** scores groundedness and
completeness on whatever survives the deterministic pass, producing a
`VerificationResult(score, is_grounded, issues, suggested_refinements)`.

FR-06: `route_after_critic` sends the graph back to `retriever_node` when
`score < settings.critic_threshold and retry_count < settings.max_correction_passes`,
otherwise forward to `briefer_node`. `retry_count` increments inside `retriever_node`
itself, not on the edge, so the count reflects retrieval attempts actually made.

FR-07: `briefer_node` assembles the final `IncidentBrief` and persists a new `briefs`
row (incrementing `version` for the incident), recording `correction_passes` and
`llm_used`.

FR-08: The whole graph degrades gracefully when no LLM is reachable — `normalizer_node`,
`analyst_node`, and the LLM half of `critic_node` all depend on
`LLMRouter`/`LLMUnavailableError` (Phase 6). When that's raised, the graph still
completes using whatever the deterministic nodes (retriever, correlator) produced,
`briefer_node` sets `brief.llm_used=false`, and the brief is genuinely useful on its
own — a ranked candidate list with explainable subscores is real value even with zero
model calls, matching plan.md §10's documented degradation ladder.

FR-09: State is checkpointed to Postgres (`AsyncPostgresSaver`, keyed by `incident_id`
as the LangGraph thread id) so a brief generation survives a worker restart, and so a
follow-up question against the same incident later can resume from persisted state
rather than starting cold — this is the project's agent-memory story.

FR-10: `app/agents/streaming.py` wraps `graph.astream_events` and yields a normalized
event stream (`node_start`, `node_end` with latency/tokens, `retry`, `done`, `error`),
writing each step to `agent_run_steps` as it happens — Phase 9's SSE endpoint consumes
this directly; this phase does not build the endpoint itself.

## User Stories

- As a responder, I want the system to tell me plainly when it couldn't reach any LLM
  and show me what deterministic correlation still found, instead of failing silently
  or returning nothing.
- As a responder reading a brief, I want to trust that every claim traces back to a real
  excerpt from a real postmortem — the critic's deterministic citation check exists so
  that trust isn't just "the model said so."
- As the author of Phase 9, I want a `TriageState`-in, `IncidentBrief`-out compiled
  graph with a checkpointer already wired, so building the incidents API is "call the
  graph and stream its events," not "figure out how citations get validated."
- As the author of Phase 12's evaluation harness, I want `correction_passes` and
  citation-validity to be inspectable outputs of a real run, not something the harness
  has to reimplement checking for itself.

## Out of Scope

- `app/services/incidents_service.py`, the `/incidents` API, and F5/F6 — Phase 9. This
  phase builds and verifies the graph via a standalone script/tests against an
  already-existing seeded `incident_id`; it does not create incidents.
- The SSE HTTP endpoint itself (`GET /incidents/{id}/brief/stream`) — Phase 9 owns
  wiring `streaming.py`'s event generator into a FastAPI route.
- Multi-turn follow-up question handling beyond "the checkpointer preserves state so
  it's technically possible" — actually driving a second turn against existing state is
  Phase 9+'s concern once there's an API to send that second turn through.
- Prompt-level evaluation/scoring beyond the critic's own pass/fail — Phase 12.

## Acceptance Criteria

1. Feeding a seeded alert through the compiled graph (via a script, per the checkpoint)
   fires all six nodes in order and produces a typed `IncidentBrief`.
2. A `normalizer_node` run against alert text naming a real service resolves it to that
   service's real id; naming a service that doesn't exist in the catalog puts it in
   `unresolved_mentions`, never a fabricated id.
3. Forcing a low critic score triggers exactly one corrective retry back to
   `retriever_node`, and the retry's query differs from the original (verifiable via the
   retry's `hybrid_search` call arguments).
4. A citation naming a `chunk_id` outside the retrieval set always fails the critic's
   deterministic check, regardless of what an LLM judge would say about it in isolation.
5. With `LLMUnavailable` raised (no key configured, matching this build's actual
   environment), the graph still completes, `brief.llm_used` is `false`, and the
   persisted brief's `matched_postmortems`/blast-radius content still reflects real
   deterministic correlator output.
6. `route_after_critic`'s truth table (score/retry_count combinations) is covered by a
   dedicated unit test independent of any actual graph run.
7. Every retrieval and correlation call is `workspace_id`-scoped — a graph run for one
   workspace's incident never touches another workspace's postmortems or services.
8. `ruff`, `mypy --strict`, and the backend test suite are all clean.
