# FRD: Evaluation Harness

## API Endpoints (Backend — FastAPI)

### `GET /workspaces/{workspace_id}/evaluation/runs`
- Auth required: yes, any role (owner/responder/viewer) — read-only.
- Request schema: query param `limit: int = 20` (most recent first).
- Response schema: `list[EvalRunOut]`.
- Error codes: 401 (no session), 404 (cross-tenant workspace id, matching every other
  module's tenant-isolation convention).

### `GET /workspaces/{workspace_id}/evaluation/runs/{run_id}`
- Auth required: yes, any role.
- Request schema: path params only.
- Response schema: `EvalRunDetailOut` (run metadata + `results: list[EvalCaseResultOut]`).
- Error codes: 401, 404 (run not found, or found but belongs to a different workspace —
  same not-found-not-forbidden pattern as every other cross-tenant lookup in this
  codebase).

## React Components (Frontend)

### `pages/Evaluation.tsx` (F11)
- Props interface: none (route component).
- API calls made: `listEvalRuns(workspaceId)`, `getEvalRun(workspaceId, runId)` for the
  currently-selected run (defaults to the most recent `full`-mode run, falling back to
  the most recent run of any mode if none exists yet).
- States managed: selected run id (for drill-down), loading/error per React Query
  convention (`useQuery`, matching `Search.tsx`/`ServiceMap.tsx` precedent).
- User interactions: click a past run in the trend chart or a mode in the ablation table
  to switch the drill-down to that run.

### `components/evaluation/MetricCards.tsx`
- Props: `run: EvalRunOut | null`.
- Renders recall@1, recall@5, MRR, citation validity, groundedness as stat cards.
  Groundedness (and citation validity, defensively) render `"—"` with a tooltip
  ("no LLM key configured") when `null`, never `0%`.

### `components/evaluation/EvalTrendChart.tsx`
- Props: `runs: EvalRunOut[]`.
- Recharts line chart, x-axis `started_at`, two lines (recall@5, MRR) — same library and
  pattern as `MttrChart.tsx` (Phase 10).

### `components/evaluation/AblationTable.tsx`
- Props: `runs: EvalRunOut[]`.
- Groups `runs` by `mode`, takes the most recent row per mode, renders one row per mode
  (`vector`, `vector_bm25`, `full`) with recall@1/recall@5/mrr side by side. A mode with
  no run yet renders "not yet run" instead of blank cells.

### `components/evaluation/CaseResultsTable.tsx`
- Props: `results: EvalCaseResultOut[]`.
- Sorted with `passed=false` rows first (failing cases are the most interesting part of
  this page per the PRD), each row shows case name, rank of first hit (or "not
  retrieved"), and groundedness if present.

## Data Model Changes

`eval_runs` gains one nullable column: `mode VARCHAR(20)` — which of `vector` /
`vector_bm25` / `full` produced this run. Additive migration, no backfill needed (no
rows exist in any real environment yet — Phase 11's seed data populates `eval_cases`
only, never `eval_runs`). Reference plan.md §8's `eval_runs` definition, which predates
this phase and didn't anticipate the ablation-mode dimension; `notes` (already on the
table) stays free-text and unused by this phase's own code, left for future manual
annotation.

No other schema changes — `eval_cases`/`eval_case_results` already match plan.md §8
exactly and were created by Phase 1's initial migration.

## Internal Architecture

### `app/services/evaluation/metrics.py` (pure, no I/O)
- `rank_of_first_hit(retrieved_ids: list[UUID], expected_ids: set[UUID]) -> int | None`
  — 1-based rank of the first retrieved id that's in `expected_ids`, or `None`.
- `recall_at_k(rank: int | None, k: int) -> bool` — `rank is not None and rank <= k`.
- `reciprocal_rank(rank: int | None) -> float` — `1/rank` if hit else `0.0`.
- `citation_validity(draft: DraftBrief, retrieval: SearchResponseOut) -> float | None` —
  thin wrapper around Phase 8's existing `app.agents.citation_check.validate_citations`;
  returns `valid_count / total_count` over all citations in the draft, `None` if the
  draft carried zero citations to check (nothing to score, not a failure).

### `app/services/evaluation/runner.py`
- `AblationMode = Literal["vector", "vector_bm25", "full"]`
- `async def _retrieve_ranked_ids(db, graph_store, *, workspace_id, query, mode, top_k)
  -> list[UUID]` — composes `search_vector`/`search_keyword`/`search_graph` per mode
  (vector-only; vector+keyword; vector+keyword+graph) and fuses with the existing
  `reciprocal_rank_fusion`, exactly mirroring `hybrid.py`'s own composition but with the
  retriever subset selected by ablation mode instead of hardcoded to all three. Vector
  and keyword each get their own fresh `AsyncSession` when run together, matching ADR
  0007 §1's concurrency rule; this function does not run them concurrently (eval isn't
  latency-sensitive the way live search is), so a single shared session is safe and
  simpler here.
- `async def _stub_draft_brief(db, *, top_postmortem_id) -> DraftBrief | None` — reuses
  the exact fact-derivation shape `app/seed/seed.py`'s `_precompute_brief` already
  established (root_cause fact → hypothesis, remediation fact → runbook step, both
  cited to their real `source_chunk_id`), scoped down to just building the
  `DraftBrief` object (no `Brief` row, no persistence) for `citation_validity` to score
  against. Returns `None` if the postmortem has no facts (nothing to validate).
- `async def _case_result(db, graph_store, router, *, workspace_id, case, mode, top_k,
  llm_configured) -> tuple[EvalCaseResult, groundedness: float | None]` — runs the
  above, computes rank/recall/citation validity, and (only if `llm_configured`) calls
  Phase 8's `judge_verification` with a minimal `NormalizedSignal` built from
  `case.incident_text`, catching `LLMUnavailableError` and degrading that one case's
  groundedness to `None` rather than failing the whole run.
- `async def run_eval(db, graph_store, router, *, workspace_id, mode, top_k=10,
  llm_configured) -> EvalRun` — loads every `EvalCase` for the workspace, runs
  `_case_result` for each, persists one `EvalCaseResult` row per case and one `EvalRun`
  aggregate row (mean of each metric; `groundedness`/`citation_validity` averaged only
  over cases that produced a value, `None` if none did), returns the persisted run.

### `app/services/evaluation/cli.py`
- `argparse` with `--mode {vector,vector_bm25,full,all}` (default `all`) and
  `--workspace-id` (default: look up the single `Workspace.is_demo` row, same lookup
  `seed.py` uses — errors with a clear "run `make seed` first" message if none exists).
- `all` runs the three real modes sequentially against the same `EvalRun` machinery,
  then prints the ablation comparison table (recall@1/recall@5/mrr per mode) and a
  Markdown-formatted version of the same table, ready to paste into the README.
- A single mode prints that run's aggregate metrics plus a per-case table, failing cases
  first.
- No `rich`/`tabulate` dependency added — plain aligned `str.format`/f-string tables,
  since nothing else in this codebase pulls in a CLI-formatting library and the output
  only needs to be readable in a terminal and pasteable as Markdown.

### `app/api/v1/evaluation.py`
- Thin router calling `evaluation_service.list_runs`/`get_run_detail` (new
  `app/services/evaluation_service.py`, the read-only query layer the API needs —
  distinct from `runner.py`, which is the write path only the CLI calls). Mirrors
  `dashboard.py`'s shape: `CurrentWorkspaceMember` dependency, no extra role check
  (every role can read).

## Dependencies

- Calls: `app.services.retrieval.{vector,keyword,graph,fusion}` (Phase 7),
  `app.agents.citation_check.validate_citations` (Phase 8),
  `app.agents.critic_agent.judge_verification` + `app.services.llm.router.LLMRouter`
  (Phase 8), `app.models.evaluation.{EvalCase,EvalRun,EvalCaseResult}` (Phase 1),
  `app.services.postgres_graph_store.PostgresGraphStore` (Phase 4).
- Called by: `make eval` (operator CLI only), F11 `Evaluation.tsx` (read-only, via the
  two new GET endpoints — never calls `runner.py` directly or indirectly).

## Sequence Flows

### `make eval MODE=all`
1. `cli.py` resolves the demo workspace id.
2. For each mode in `[vector, vector_bm25, full]`: `runner.run_eval(...)` loads the 20
   `EvalCase` rows, retrieves + scores each, persists `EvalCaseResult` rows and one
   `EvalRun` row.
3. `cli.py` prints the three runs' metrics as a comparison table and a Markdown block.

### F11 page load
1. `Evaluation.tsx` calls `GET .../evaluation/runs` → renders trend chart + ablation
   table (grouped client-side by `mode`) from the list.
2. Selects the most recent `full`-mode run (or the most recent run of any mode as a
   fallback) and calls `GET .../evaluation/runs/{id}` → renders metric cards +
   case-results drill-down.

## Edge Cases & Error Handling

- **No `EvalCase` rows in the workspace** (e.g. `make seed` never run): `run_eval`
  raises a clear `AppError` rather than silently persisting a zero-case run; `cli.py`
  surfaces this as "no eval cases found — run `make seed` first."
- **A case's `expected_postmortem_ids` is empty**: `rank_of_first_hit` is trivially
  `None` (nothing to match) — counted as a miss, not skipped, since an eval case with no
  ground truth would otherwise silently inflate recall by being excluded.
- **No LLM key configured**: every case's `groundedness` is `None`; the aggregate
  `EvalRun.groundedness` is `None`; CLI prints "groundedness: skipped (no LLM key)" and
  the F11 card shows "—", never `0%`.
- **A retrieved postmortem has zero facts** (shouldn't happen against the real seeded
  corpus, but a hand-built fixture in a test could hit it): `_stub_draft_brief` returns
  `None`, that case's `citation_validity` is `None`, excluded from the run's average the
  same way a missing groundedness value is.
- **Cross-tenant run id**: `GET .../runs/{run_id}` 404s if the run's `workspace_id`
  doesn't match the path's `workspace_id`, matching every other module's convention —
  never a 403 that would confirm the id exists in another tenant.
