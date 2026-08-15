# FRD: Service Catalog & Graph Traversal

## API Endpoints (Backend — FastAPI)

All routes are mounted under `/api/v1/workspaces/{workspace_id}/catalog` (nested under
the workspace, matching `get_current_workspace`'s existing tenancy pattern) except
where noted. Auth: `get_current_workspace` (any member) for reads;
`require_role(OWNER, RESPONDER)` for writes.

### `GET /teams`
List teams in the workspace.

### `POST /teams`
- Auth: owner/responder
- Request: `TeamCreate{name, slack_handle?, escalation_contact?}`
- Response `201`: `TeamOut`

### `PATCH /teams/{team_id}`, `DELETE /teams/{team_id}`
- Auth: owner/responder
- Errors: `404` (team not in this workspace)

### `GET /services`
- Query: `team_id?`, `tier?` (optional filters)
- Response `200`: `list[ServiceOut]`

### `POST /services`
- Auth: owner/responder
- Request: `ServiceCreate{name, tier, team_id?, repo_url?, description?, runbook_url?}`
- Response `201`: `ServiceOut`
- Errors: `409` (duplicate `(workspace_id, name)`)

### `GET /services/{service_id}`, `PATCH /services/{service_id}`, `DELETE /services/{service_id}`
- Auth: read = any member, write = owner/responder
- Errors: `404`

### `GET /services/{service_id}/blast-radius?depth=`
- Auth: any member
- Query: `depth: int = 4` (1-10)
- Response `200`: `BlastRadiusOut{services: list[BlastRadiusEntry]}`
  (`BlastRadiusEntry{service: ServiceOut, score: float, path: list[ServiceOut],
  depth: int}`, ordered by `score` descending)

### `GET /edges`
List edges in the workspace.

### `POST /edges`
- Auth: owner/responder
- Request: `EdgeCreate{from_service_id, to_service_id, kind, criticality}`
- Response `201`: `EdgeOut`
- Errors: `422` (self-edge — Pydantic validator, not a DB round-trip), `409` (duplicate
  `(from, to, kind)`), `404` (either service not in this workspace)

### `DELETE /edges/{edge_id}`
- Auth: owner/responder

### `POST /import`
- Auth: owner/responder
- Request: `CatalogImport{teams: list[TeamImport], services: list[ServiceImport],
  edges: list[EdgeImportByName]}` — edges reference services **by name**
  (`from_service_name`, `to_service_name`), resolved against the `services` in the same
  payload (or already in the workspace) within one transaction.
- Response `200`: `CatalogImportResult{teams_created, services_created, edges_created}`
- Errors: `422` (an edge references a service name not present in the payload or the
  existing workspace catalog — the whole import rolls back, nothing partially applied)

### `GET /graph`
- Auth: any member
- Response `200`: `CatalogGraphOut{nodes: list[ServiceOut], edges: list[EdgeOut]}` — the
  full node/edge set, shaped for a visualization client (Phase 10 consumes this
  directly; this phase ships no UI).

All error responses use the existing `{"error": {"code","message","detail"}}` envelope.

## React Components (Frontend)

None — this phase is backend-only per Master-Prompt.md's phase breakdown. The Service
Map UI that consumes `GET /graph` and `GET /services/{id}/blast-radius` is Phase 10.

## Data Model Changes

None — `teams`, `services`, `service_edges` already exist from Phase 1's initial
migration, matching plan.md §8 exactly (verified against
`backend/app/models/catalog.py`). This phase adds no new tables or columns.

## Internal Architecture

### `app/services/graph_store.py` — the `GraphStore` Protocol

```python
class GraphPath(BaseModel):
    service_ids: list[UUID]  # root ... target, inclusive

class BlastRadiusEntry(BaseModel):
    service_id: UUID
    score: float
    path: GraphPath
    depth: int

class BlastRadius(BaseModel):
    entries: list[BlastRadiusEntry]  # sorted by score desc

class GraphStore(Protocol):
    async def upstream(self, workspace_id, service_ids, max_depth=4) -> list[GraphPath]: ...
    async def downstream(self, workspace_id, service_ids, max_depth=4) -> list[GraphPath]: ...
    async def neighborhood(self, workspace_id, service_ids, k=2) -> set[UUID]: ...
    async def blast_radius(self, workspace_id, service_ids, max_depth=4) -> BlastRadius: ...
    async def shortest_path(self, workspace_id, a, b) -> GraphPath | None: ...
```

### `app/services/postgres_graph_store.py` — the recursive-CTE implementation

The shared shape for `upstream`/`downstream` (direction flips which side of
`service_edges` is followed):

```sql
WITH RECURSIVE reach(service_id, depth, path, criticality_path) AS (
    SELECT s.id, 0, ARRAY[s.id], ARRAY[]::edge_criticality[]
    FROM services s
    WHERE s.id = ANY(:start_ids) AND s.workspace_id = :workspace_id

    UNION ALL

    SELECT e.to_service_id, r.depth + 1, r.path || e.to_service_id,
           r.criticality_path || e.criticality
    FROM reach r
    JOIN service_edges e ON e.from_service_id = r.service_id
    WHERE e.workspace_id = :workspace_id
      AND r.depth < :max_depth
      AND NOT (e.to_service_id = ANY(r.path))   -- cycle guard
)
SELECT DISTINCT ON (service_id) service_id, depth, path, criticality_path
FROM reach
ORDER BY service_id, depth ASC;                  -- shortest path wins a diamond
```

`upstream` swaps `e.from_service_id = r.service_id` / selects `e.from_service_id` (walks
edges backwards). `neighborhood(k)` is the same query with `max_depth = k` and returns
the distinct `service_id` set instead of full paths. `shortest_path(a, b)` is the same
CTE seeded from `a`, `WHERE service_id = b`, `LIMIT 1`, no depth cap (bounded instead by
a generous hard ceiling, e.g. 20, to guarantee termination on a workspace with no path).

**Cycle safety.** `NOT (e.to_service_id = ANY(r.path))` is the load-bearing line — it
guarantees `reach` can only ever grow to at most (number of services in the workspace)
rows, so a cycle in the data terminates the recursion instead of looping. **Diamond
correctness.** The `DISTINCT ON (service_id) ... ORDER BY service_id, depth ASC` keeps
only the shortest path to each reached service, so a service reachable by two different
paths (a diamond) is counted once, via its shorter path.

**Blast radius scoring.** For each entry: `score = Σ over edges in path of
edge_weight(criticality) * tier_weight(reached_service.tier) / depth`, where
`edge_weight(hard) = 1.0`, `edge_weight(soft) = 0.4`, and `tier_weight` favors lower
(more critical) tiers. The exact weights are a documented, tunable constant set in
`postgres_graph_store.py`, not hardcoded inline — see the ADR for the full rationale
and the annotated SQL (plan.md's own callout on this exact design choice).

### `app/services/catalog_service.py`

`create_team`/`update_team`/`delete_team`, `create_service`/`update_service`/
`delete_service`, `create_edge` (validates non-self-edge before hitting the DB;
catches the unique-constraint `IntegrityError` and re-raises as `ConflictError`),
`delete_edge`, `import_catalog` (one transaction: teams → services → edges-by-name,
name resolution against both the payload and pre-existing workspace services).

### `app/api/v1/catalog.py`

Thin FastAPI router matching the Endpoints section above; auth via `get_current_workspace`
/`require_role`, delegates all logic to `catalog_service`/`graph_store`.

### `app/schemas/catalog.py`

The Pydantic v2 request/response models listed under Endpoints.

## Dependencies

Depends on Phase 1's `Team`/`Service`/`ServiceEdge` models and Phase 2's
`get_current_workspace`/`require_role` dependencies (unchanged). Every later module
that needs graph traversal (correlator B10, brief generation B11, Service Map UI F9)
depends on this phase's `GraphStore` protocol.

## Sequence Flows

**Blast radius query**
1. `GET /services/{id}/blast-radius?depth=3` → `get_current_workspace` resolves
   membership (404 if not a member) → `graph_store.blast_radius(workspace_id,
   [service_id], max_depth=3)`.
2. The recursive CTE walks `service_edges` forward from `service_id`, cycle-guarded,
   depth-capped at 3.
3. Each reached row is scored (criticality × tier ÷ depth) and mapped to
   `BlastRadiusEntry` with its explanatory path; the route sorts by score and returns.

**Catalog import**
1. `POST /import` with `{teams: [...], services: [...], edges: [...]}`.
2. `catalog_service.import_catalog` opens one transaction: inserts teams, then
   services (each `ServiceImport.team_name` resolved to the just-inserted team's ID or
   an existing one), then edges (each `from_service_name`/`to_service_name` resolved
   against the service name→ID map built in the previous step).
3. Any resolution failure (an edge names a service that doesn't exist anywhere in the
   payload or the workspace) raises `ValidationAppError` and the whole transaction
   rolls back — partial imports never happen.

## Edge Cases & Error Handling

| Edge case | Handling |
|---|---|
| Self-edge (`from_service_id == to_service_id`) | `422` — rejected by a Pydantic validator on `EdgeCreate`, never reaches the DB |
| Duplicate `(from, to, kind)` edge | `409 conflict`, mapped from the DB's existing unique constraint |
| Edge references a service in a different workspace | `404` — services are re-fetched scoped to `workspace_id`, so a cross-workspace ID looks like "not found" |
| Cycle in the dependency graph | Traversal terminates via the `path` array cycle guard; no request ever hangs |
| Diamond dependency | Counted once, via the shortest of its two paths (`DISTINCT ON` + `ORDER BY depth`) |
| `depth` beyond the actual graph's reach | Returns whatever was actually reached — not an error, just a smaller result |
| Import references an unknown service name | `422`, whole import rolled back, no partial catalog created |
| `viewer` calls any write endpoint | `403`, via `require_role(OWNER, RESPONDER)` |
| Non-member queries any catalog endpoint | `404`, via the existing `get_current_workspace` dependency |
