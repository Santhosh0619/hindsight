# NFR: Service Catalog & Graph Traversal

## Performance

- The graph is small and highly relational (plan.md §7: hundreds of services,
  thousands of edges) — a recursive CTE traverses it in single-digit milliseconds at
  this scale, which is the entire justification in plan.md for not using a dedicated
  graph database. This phase's tests include a fixture large enough (~10 services) to
  exercise real recursion, not just trivial one-hop cases.
- Every graph query is depth-capped (default 4, max 10) so a pathological/misconfigured
  graph can't produce an unbounded result set or an unbounded query plan.
- `GET /graph` returns the full node/edge set in one query each (no N+1) — services and
  edges are fetched with two flat, indexed, `workspace_id`-scoped queries, not a
  per-service loop.

## Security

- Every catalog/graph query is filtered by `workspace_id` — enforced at the
  service-layer function boundary (every `catalog_service`/`graph_store` function takes
  `workspace_id` as a required parameter and includes it in every WHERE clause), not
  left to the route to remember. This is the same enforcement discipline Phase 1/2
  established for `get_current_workspace`.
- Read access (list/get/traverse) requires only workspace membership; write access
  (create/update/delete/import) requires `owner` or `responder` via the existing
  `require_role` dependency — no new RBAC mechanism introduced.
- Bulk import (`POST /import`) is transactional specifically so a partially-invalid
  payload can never leave the catalog in an inconsistent state that a later query
  would silently traverse incorrectly.

## Reliability

- Cycle-safety is structural (the `path` array guard in the recursive CTE), not
  best-effort — a cycle in imported or hand-entered data can never hang a request or
  exhaust the connection pool.
- `create_edge` catches the DB's unique-constraint violation and maps it to a clean
  `409`, rather than letting a raw `IntegrityError` surface as a 500.

## Observability

- `structlog` events for catalog mutations: `service_created`, `edge_created`,
  `catalog_imported` (with counts), at `info` level, matching Phase 2's established
  pattern for mutation logging.

## Testability

- Backend: `test_graph.py` covers the checkpoint's explicit cases — linear chain depth
  correctness, diamond dependency counted once, a cycle terminates (assert the request
  completes, not just that it returns *something*), `hard` vs `soft` criticality
  ordering, depth cap respected. `test_catalog.py` covers CRUD, the RBAC role matrix
  (viewer 403 on writes), cross-tenant 404, self-edge rejection, duplicate-edge 409,
  and import (happy path + rollback on an unresolvable service name).
- All tests run against a real Postgres (same pattern as Phase 2 — recursive CTE
  correctness can't be meaningfully verified against a mock).

## Constraints

- Everything from Phases 1-2's NFRs still applies (async throughout, Pydantic v2 at
  every boundary, typed exceptions, `mypy --strict` clean, no bare dicts).
- No new database tables/migrations — this phase builds entirely on Phase 1's existing
  `teams`/`services`/`service_edges` schema.
- No graph database, no separate graph query language — Postgres recursive CTEs only,
  per plan.md §7's explicit one-database rationale.
