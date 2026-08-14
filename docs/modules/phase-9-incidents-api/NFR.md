# NFR: Incidents API + The Money Screen

## Performance

- `_enrich_brief` resolves every chunk/postmortem a brief references via exactly two
  batched queries (one `IN` for chunks, one `IN` for postmortems), regardless of how
  many hypotheses/citations/matched postmortems the brief has — never N+1, matching
  the discipline already established in Phase 4's blast-radius path resolution and
  Phase 7's search-result assembly.
- Brief generation (both `POST .../brief` and the SSE stream) is inherently as slow as
  the graph itself (up to `1 + max_correction_passes` full retrieval+LLM cycles) — no
  additional latency this phase adds on top of Phase 8's own cost.
- `GET /incidents` uses the same cursor-pagination shape as `GET /postmortems`
  (`tuple_(created_at, id) < cursor`), so list performance doesn't degrade with corpus
  size the way offset pagination would.

## Security

- Every incidents/briefs/feedback query is `workspace_id`-scoped at the service-layer
  boundary, matching the discipline established since Phase 1 — a member of workspace A
  can never read or mutate workspace B's incidents, briefs, or feedback.
- Brief generation (`POST .../brief`, `GET .../brief/stream`) and incident mutation
  (`POST`/`PATCH /incidents`) are gated to owner/responder via the existing
  `require_role` dependency — a viewer can read F6/F7 but triggers nothing that costs
  an LLM call or mutates state, matching Phase 3's already-proven RBAC pattern.
- The SSE stream is authenticated exactly like every other endpoint (`Authorization:
  Bearer` header via `fetch()`, not a query-string token) — no new credential-leak
  surface introduced to support streaming. See FRD Gap #3.
- `raw_alert_text` is arbitrary user-submitted text fed to an LLM (via `normalizer_node`
  and `analyst_node`'s prompts) — the same untrusted-data delimiting Phase 6/8 already
  established applies unchanged; this phase adds no new prompt-construction code that
  bypasses it.

## Reliability

- A client disconnecting mid-SSE-stream doesn't leave the `AgentRun` row stuck
  `running` forever — `stream_brief_generation` marks it `done`/`error` in a
  `finally` block regardless of whether anything is still listening.
- Every `LLMUnavailableError` path Phase 8 already handles (empty signal, empty draft,
  pass-through verification) surfaces through this phase's API as a completed brief
  with `llm_used=false`, never as an HTTP error — brief generation genuinely degrades,
  it doesn't fail, matching plan.md §10's documented "no key at all" level.
- `_enrich_brief` never raises on a citation whose chunk/postmortem no longer resolves
  (e.g. deleted between generation and read) — it's silently omitted from the enriched
  response rather than 500ing the whole brief.

## Observability

- `structlog` events: `incident_created`, `brief_generation_started`,
  `brief_generation_completed` (with `incident_id`, `llm_used`, `correction_passes`,
  duration) in `incidents_service.py` — this is where Phase 8's own deferred
  `agent_run_started`/`agent_run_completed` bracketing actually lands. Phase 8's NFR
  explicitly deferred it here: "this phase has no single invocation entrypoint of its
  own... Phase 9's `incidents_service.generate_brief` is this graph's first real caller
  and where that bracketing belongs."

## Testability

- Backend: `test_incidents_api.py` covers CRUD + RBAC + cross-tenant isolation
  (mirroring every prior phase's endpoint test shape). `test_incidents_service.py`
  covers `generate_brief`/`stream_brief_generation` against `pydantic-ai`'s
  `TestModel`/`FunctionModel` (Phase 6/8's established pattern, never a real network
  call) — a full happy-path brief, a forced retry visible in the SSE event sequence,
  and an `LLMUnavailable` degradation, verifying `llm_used`/`correction_passes` land
  correctly on the persisted and returned brief. `test_enrich_brief.py` covers the
  citation/postmortem batch-resolution logic against hand-built fixtures, including the
  "a referenced chunk no longer exists" edge case.
- Frontend: component tests for `AgentPipelineTrace` (node state transitions driven by
  mock events, including a retry resetting downstream nodes) and `BriefView`
  (hypothesis/citation/matched-postmortem/blast-radius/runbook rendering, badge
  visibility). E2E (Playwright, against the isolated test stack) covers the real
  acceptance-criteria loop: create an incident, watch the live trace, see a rendered
  brief with citations, submit feedback — in a real browser, matching Phase 3/7's
  established e2e discipline. Graph mode's dependence on ingested/extracted corpus data
  means the e2e fixture ingests real postmortems first (same `_ingest` helper pattern
  Phase 7/8 already established) so there's something real for the brief to match
  against.

## Constraints

- Everything from Phases 1-8's NFRs still applies (async throughout, Pydantic v2 at
  every boundary, typed exceptions, `mypy --strict` clean, no bare dicts, `workspace_id`
  filtering on every tenant-scoped query, TypeScript strict on the frontend, React
  Query for server state).
- No new database tables or migrations — every table this phase touches existed since
  Phase 1.
- No new backend dependencies — `sse-starlette` has been a dependency since Phase 1
  (unused until now), everything else this phase needs already shipped in Phase 8.
- No new frontend dependencies — the SSE consumer is hand-rolled (`lib/sse.ts`)
  specifically to avoid adding a library for something this focused, matching this
  project's existing restraint about dependency additions.
