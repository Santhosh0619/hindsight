# NFR: Evaluation Harness

## Performance

- `run_eval` for one mode against the real 20-case corpus must complete well within
  `make eval`'s implicit "fast enough to run before every README update" bar — no hard
  SLA, but each case is bounded by one retrieval call (vector/keyword/graph, already
  proven fast in Phase 7) plus, at most, one LLM judge call when a key is configured.
  Cases run sequentially, not concurrently — same reasoning as `dashboard_service.py`'s
  `_fragile_services` loop (ADR 0007 §1 / ADR 0008 §4): every case shares the caller's
  one `AsyncSession`, and this is an operator-run batch job, not a request handler, so
  there's no latency budget forcing concurrency.
- The two read endpoints (`GET .../runs`, `GET .../runs/{id}`) are simple indexed
  lookups (`eval_runs.workspace_id`, `eval_case_results.eval_run_id` — both already
  indexed per plan.md §8) with no retrieval/LLM work in the request path at all.

## Security

- Auth enforcement point: `CurrentWorkspaceMember` dependency on both endpoints, same as
  every other tenant-scoped GET route in this codebase. No role restriction beyond
  membership — a viewer can read eval results, matching plan.md §5's viewer definition
  ("read dashboards, incidents, briefs, search" — evaluation results are the same class
  of read-only operational visibility).
- Tenant isolation: both endpoints filter `EvalRun.workspace_id == workspace_id`
  (list) and additionally re-check it on the detail lookup before returning 200 (404
  otherwise) — the standard cross-tenant-404 pattern audited in every prior phase.
- `run_eval` itself has no HTTP surface — it's only reachable via `cli.py`, run by an
  operator with direct database/container access, so it needs no additional auth layer
  of its own (same trust boundary as `make seed`).
- No secrets touched. `citation_validity`'s stub-brief derivation reads already-redacted
  `postmortem_chunks.content` (Phase 5's redaction already ran at ingest time), never
  `raw_text`.

## Reliability

- Groundedness degrades to `None` per-case and in aggregate whenever
  `settings.llm_configured` is false, or whenever every configured provider raises
  `LLMUnavailableError` mid-run — a quota exhaustion partway through the 20 cases must
  not crash the run or silently zero out the remaining cases' other metrics
  (recall/MRR/citation validity are unaffected, since they don't touch the LLM at all).
- `run_eval` is not required to be idempotent/resumable the way `seed.py` is — each
  invocation is a fresh, independently-persisted `EvalRun` row by design (the trend
  chart's whole point is showing successive runs over time), so no get-or-create check
  against prior runs.

## Observability

- `structlog` events: `eval_run_started` (workspace_id, mode, case_count),
  `eval_case_scored` (case_name, rank_of_first_hit, citation_validity, groundedness —
  one per case, at `debug` level to avoid flooding a 20-case run's logs at `info`),
  `eval_run_completed` (workspace_id, mode, recall_at_1, recall_at_5, mrr,
  citation_validity, groundedness, duration_ms). Mirrors the
  `postmortem_ingested`/`search_completed` precedent from Phases 5/7 — one clear
  start/end pair plus a per-item detail event.
- `llm_provider_failed` (already emitted by `LLMRouter._try_providers`, Phase 6) fires
  naturally when groundedness scoring hits an unconfigured/exhausted provider — no new
  logging needed there, just don't let it propagate out of `_case_result`.

## Testability

- Backend unit tests: `metrics.py`'s four functions against hand-computed fixtures
  (known retrieved-id lists, known expected sets) — pure functions, no DB.
- Backend integration tests: `runner.py`'s `run_eval` against the real dev Postgres with
  a small hand-built fixture (2-3 services, 2-3 postmortems with facts, 3-4 eval cases
  with known expected matches) for each of the three modes, asserting the persisted
  `EvalRun`/`EvalCaseResult` rows match hand-computed recall/MRR — not run against the
  full 80-postmortem seeded corpus (too slow and non-deterministic to assert exact
  numbers against; the seeded-corpus run is a manual verification step, not a pytest
  fixture). `pydantic-ai`'s `FunctionModel`/`TestModel` (Phase 6/8 precedent) mocks the
  groundedness judge call — no test hits a real network.
- Frontend component tests: `MetricCards`/`AblationTable`/`CaseResultsTable`/
  `EvalTrendChart` each get a `vitest` test asserting the null-groundedness "—" render,
  the failing-cases-first sort, and the per-mode grouping.
- E2E: `e2e/tests/evaluation.spec.ts` — seed at least one real `EvalRun` via the API
  test stack's own `docker-compose.test.yml` fixture setup (not the CLI, which isn't
  exercised by Playwright), then verify F11 renders cards/table/drill-down against it.

## Constraints

- No LLM call in a request handler (CLAUDE.md) — both new endpoints are pure reads of
  already-persisted rows; the only LLM call in this entire module (`judge_verification`
  inside `run_eval`) only ever runs from `cli.py`, never from a FastAPI route.
- Async throughout; full type hints; mypy strict clean.
- Every tenant-scoped query filters `workspace_id`, enforced at the repository/service
  layer per plan.md §8, not left to the route layer alone.
