# NFR: LangGraph Agent Pipeline

## Performance

- `correlator_node`'s failure-mode overlap computation is one batched query over
  `postmortem_failure_modes` for every candidate's `postmortem_id` at once, not N+1
  queries per candidate.
- The semantic cache check in `analyst_node` is a cheap exact-hash lookup before any
  embedding call (Phase 6's existing `get_cached` behavior) — a repeated/near-duplicate
  incident prompt (the seeded-demo-replay case plan.md §10 describes) never pays for a
  live LLM call on a cache hit.
- `streaming.py` writes one `AgentRunStep` row per node per run, not per token — bounded
  by the six-node graph size regardless of how much retry looping happens (each retry
  adds at most a few more rows, never unbounded).

## Security

- Every node that touches the database takes `workspace_id` from `TriageState` (set
  once at graph invocation, never re-derived mid-run) and every query it issues is
  scoped by it — `correlator_node`'s blast radius, failure-mode overlap query, and
  `normalizer_node`'s catalog lookup all inherit the same discipline established since
  Phase 1.
- `analyst_node`'s prompt fences retrieved postmortem content with the same
  `UNTRUSTED_DATA_NOTICE` Phase 6 established — retrieved text is data to cite, never
  instructions to follow, regardless of what a malicious/injected postmortem claims.
  `injection_flagged` postmortems aren't excluded from retrieval (Phase 5 never blocked
  ingestion on that flag either) — the delimiting is the actual defense, not exclusion.
- `critic_node`'s deterministic citation check is a hard gate independent of the LLM
  judge — an invalid citation is dropped even if an LLM judge would have called it fine,
  so the guarantee doesn't depend on a model behaving well.

## Reliability

- Every LLM-calling node (`normalizer`, `analyst`, `critic`'s judge stage) catches
  `LLMUnavailableError` locally and degrades (empty signal / empty draft / pass-through
  verification) rather than letting the exception propagate and crash the whole graph
  run — FR-08's degradation contract is enforced at each call site, not by a single
  try/except wrapped around the entire graph.
- `route_after_critic` never retries when `llm_used=False` — a retry against a
  still-unavailable LLM would just burn `max_correction_passes` for nothing.
- The Postgres checkpointer means a worker restart mid-run doesn't lose progress —
  verified live this phase against the real dev database (see the ADR), not just
  assumed from the library's documentation.

## Observability

- `structlog` events: `agent_run_started`/`agent_run_completed` (with `incident_id`,
  `llm_used`, `correction_passes`, total latency) bracketing a full graph invocation,
  matching every prior phase's completion-logging pattern.
- `agent_run_steps` rows (written by `streaming.py`) are this phase's detailed
  per-node audit trail — inspectable independent of the structured logs, and exactly
  what Phase 9's SSE stream and F5's live pipeline visualization will read from.

## Testability

- `route_after_critic`'s full truth table (score above/below threshold ×
  retry_count above/below max × `llm_used` true/false) is unit-tested as a pure
  function — no graph execution needed for this one.
- `correlator_node` is tested against hand-built `SearchResponseOut`/failure-mode
  fixtures with zero network or LLM access — every subscore's expected value is
  computable by hand from the fixture, matching Phase 7's `test_fusion.py` precedent
  for pure-logic testability.
- `critic_node`'s deterministic citation check is tested directly: a citation naming a
  real `chunk_id` that was never actually retrieved always fails, independent of any
  LLM — mirrors Phase 6's `FunctionModel`-based injection-defense test in spirit
  (proving the guard actually guards, not just that the pipeline runs).
- The full graph is tested end-to-end with `pydantic-ai`'s `TestModel`/`FunctionModel`
  (Phase 6's established pattern, not hand-rolled fakes) standing in for
  `LLMRouter` — one test forces a low critic score and asserts exactly one retry
  fires before `briefer`; one test raises `LLMUnavailableError` from every LLM call
  and asserts the graph still completes with `llm_used=False` and real deterministic
  content in the persisted brief. No test in this phase makes a real network call.
- The Phase 0/6 discipline of re-verifying a fast-moving library's actual API before
  writing code against it was repeated here: `AsyncPostgresSaver.from_conn_string`/
  `.setup()` and `StateGraph`/`add_conditional_edges`/`astream_events` were all
  introspected and smoke-tested live against the installed `langgraph` 1.2.11 /
  `langgraph-checkpoint-postgres` 3.1.2 (matching ADR 0000's original findings exactly
  — no drift since Phase 0) before any node code was written.

## Constraints

- Everything from Phases 1-7's NFRs still applies (async throughout, Pydantic v2 at
  every boundary, typed exceptions, `mypy --strict` clean, no bare dicts,
  `workspace_id` filtering on every tenant-scoped query).
- No new database tables or migrations — `incident_signals`, `briefs`, and
  `agent_run_steps` all existed since Phase 1; this phase is their first writer.
- `psycopg[binary]` and `langgraph-checkpoint-postgres` are new explicit backend
  dependencies (confirmed necessary and version-matched against ADR 0000's Phase 0
  findings) — both `api` and `worker` images need rebuilding, not just a live
  `pip install`, for the dependency to actually be baked in (same lesson as Phase 6's
  `groq` addition).
- No new frontend code this phase (PRD Out of Scope) — nothing here to type-check,
  lint, or build on the frontend side.
