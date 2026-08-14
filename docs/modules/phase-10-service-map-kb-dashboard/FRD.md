# FRD: Service Map, Knowledge Base, Dashboard

## Gaps this phase had to resolve

1. **The postmortem API exposes none of Phase 6's extraction output.** `PostmortemOut`/
   `PostmortemDetailOut` carry status/severity/chunks — nothing from `PostmortemFact`,
   `PostmortemService`, or `redacted_text` itself. FR-06 needs the full document text
   to render, plus every fact highlighted at its source location; FR-04's table needs
   each postmortem's affected services. Extended `PostmortemDetailOut` with
   `redacted_text: str | None` and `facts: list[PostmortemFactOut]` (resolved via each
   fact's `source_chunk_id` → that chunk's `char_start`/`char_end`, since
   `PostmortemFact` has no offsets of its own — a fact's evidence is "somewhere in this
   chunk," the same granularity Phase 9 already established for citations). Extended
   `PostmortemOut` itself (used by both the list and detail views) with
   `affected_services: list[PostmortemServiceLinkOut]`, resolved via one batched query
   across every postmortem on a list page — never N+1, mirroring `_enrich_brief`'s
   batching pattern from Phase 9.
2. **No LLM key is configured in this build session** (the same standing choice as
   every prior phase since Phase 6). `extract_postmortem` jobs dead-letter after
   retrying, so `postmortem_facts`/`postmortem_services`/`postmortem_failure_modes`
   stay empty for every postmortem ingested through the real pipeline in this
   environment. FR-06's fact-highlighting and FR-04's affected-services column both
   degrade to an honest empty state ("No facts extracted yet" / no chips) rather than
   fabricating anything — backend tests that need real fact/link rows to exercise the
   resolution logic insert them directly via the DB, the same approach Phase 9's
   `test_enrich_brief.py` used for citations.
3. **Nothing aggregates across incidents/postmortems/services for the Dashboard.**
   Every existing endpoint is scoped to one entity (one incident's briefs, one
   service's blast radius). FR-07 through FR-10 need workspace-wide aggregates that
   don't correspond to any existing service function. New `app/services/
   dashboard_service.py` + `app/schemas/dashboard.py` + a single `GET
   /workspaces/{workspace_id}/dashboard` endpoint, computed fresh on every request (no
   caching table this phase — corpus sizes here are small enough that a handful of
   aggregate queries costs single-digit milliseconds; revisit if Phase 11's real seed
   scale changes that).
4. **"Fragility" isn't defined anywhere** — Master-Prompt.md says "ranked by incident
   count weighted by blast radius," which names two numbers without saying how to
   combine them. Defined as `fragility_score = incident_count × (1 + blast_radius_
   size)`, where `incident_count` is the number of incidents whose `IncidentSignal.
   affected_service_ids` includes this service (across every signal on the incident,
   matching the same "any historical signal, not only the latest" simplification
   Phase 9 already documented for its own `service_id` filter), and `blast_radius_size`
   is the count of entries `PostgresGraphStore.blast_radius` returns for that service
   at the default depth. The `+ 1` means a service with zero downstream dependencies
   still scores by its raw incident count instead of collapsing to zero — a
   single-node service that keeps breaking is still fragile, just not *contagious*.
5. **"Layered/force layout" is ambiguous, and a real force-directed simulation is the
   wrong tool here.** A physics-based layout (repulsion + spring edges, iterated to a
   stable state) is non-deterministic between renders, expensive to keep smooth at 40
   nodes without a real simulation library (explicitly out of scope — "no paid
   library," and a hand-rolled physics loop is a lot of new surface for a cosmetic
   requirement), and hard to test (`toMatchSnapshot` on node positions would be
   flaky). Implemented a deterministic **layered layout** instead: each service's layer
   is the length of its longest acyclic path from a root (a service with no incoming
   edges, or — if the graph has no such service, e.g. a pure cycle — the service with
   the fewest incoming edges, breaking ties by name for determinism), computed with a
   cycle-safe longest-path walk (a node already on the current path is treated as a
   back-edge and skipped, never revisited, so a cycle can't loop the algorithm forever
   — matching the same "the catalog graph can have cycles" assumption Phase 4's own
   traversal code already made). Nodes within a layer are spaced evenly; layers are
   spaced along one axis. Fully deterministic given the same graph, and unit-testable
   against hand-built fixtures (chain / diamond / cycle) the same way Phase 4's
   `test_graph.py` tested traversal itself.
6. **Blast radius highlighting on the map (FR-02) reuses Phase 4's existing endpoint
   as-is** — `GET /catalog/services/{id}/blast-radius` already returns exactly the set
   of downstream service ids and their path, resolved with names/tiers. No new
   endpoint; the map just calls it on node click and colors the returned ids red.
7. **Recent-briefs (FR-10) needs a workspace-wide query Phase 9 never wrote** — Phase
   9's `list_briefs` is scoped to one `incident_id`. Added `list_recent_briefs(db, *,
   workspace_id, limit)` to `incidents_service.py` (not a new module — it's the same
   `Brief`/`Incident` join Phase 9 already owns), ordered by `generated_at desc nulls
   last`, joined to `Incident` for the title. Reuses the existing `BriefOut`-adjacent
   resolution only as far as the dashboard card needs (incident id/title, brief id/
   version/confidence/generated_at) — a new lightweight `RecentBriefOut`, not the full
   enriched `BriefOut` (the dashboard card doesn't render hypotheses or citations).

## API Endpoints (Backend — FastAPI)

### `GET /workspaces/{workspace_id}/catalog/graph` — unchanged (Phase 4)
Already returns every service + edge; Service Map's only graph data source.

### `GET /workspaces/{workspace_id}/catalog/teams` — unchanged (Phase 4)
Resolves `team_id` → name for the map's "color by team" legend and the side panel's
owner contact info.

### `GET /workspaces/{workspace_id}/catalog/services/{id}/blast-radius` — unchanged (Phase 4)
Drives the side panel's blast-radius list and the map's red-highlight set.

### `GET /workspaces/{workspace_id}/incidents?service_id=...` — unchanged (Phase 9)
Drives the side panel's incident history.

### `GET /workspaces/{workspace_id}/postmortems` — extended response shape
`PostmortemOut` gains `affected_services: list[PostmortemServiceLinkOut]`. Query
params unchanged (`status`, `cursor`, `limit`).

### `GET /workspaces/{workspace_id}/postmortems/{id}` — extended response shape
`PostmortemDetailOut` gains `redacted_text: str | None` and
`facts: list[PostmortemFactOut]`, each fact carrying its resolved `char_start`/
`char_end` for the highlight renderer.

### `GET /workspaces/{workspace_id}/dashboard` — new
Returns `DashboardOut`: `open_incidents: int`, `briefs_generated: int`,
`corpus_size: int`, `ingest_health: IngestHealthOut` (postmortem counts by status),
`mttr_trend: list[MttrPointOut]` (last 8 ISO weeks, `mttr_minutes: float | None` — null
for a week with zero resolutions, never fabricated as 0), `fragile_services:
list[FragileServiceOut]` (top 10 by `fragility_score`), `recent_briefs:
list[RecentBriefOut]` (last 10 by `generated_at`).

## Internal Architecture

### `app/schemas/postmortem.py` (extended)
```python
class PostmortemServiceLinkOut(BaseModel):
    service: ServiceOut
    role: ServiceLinkRole
    confidence: float | None

class PostmortemFactOut(BaseModel):
    fact_type: FactType
    statement: str
    confidence: float | None
    source_chunk_id: uuid.UUID
    char_start: int
    char_end: int

class PostmortemOut(BaseModel):
    # ...existing fields...
    affected_services: list[PostmortemServiceLinkOut]

class PostmortemDetailOut(PostmortemOut):
    chunks: list[PostmortemChunkOut]
    redacted_text: str | None
    facts: list[PostmortemFactOut]
```

### `app/services/postmortem_service.py` (extended)
- `list_postmortems` now batch-resolves `affected_services` for every row on the page
  in one query (`PostmortemService` joined to `Service`, grouped by `postmortem_id`),
  not per-row.
- `get_postmortem_detail(db, workspace_id, postmortem_id) -> PostmortemDetailOut` (new)
  — wraps the existing `get_postmortem`/`list_chunks`, adds one query for
  `PostmortemFact` rows joined to their `source_chunk_id`'s `char_start`/`char_end`.

### `app/schemas/dashboard.py` (new)
```python
class IngestHealthOut(BaseModel):
    indexed: int
    processing: int
    pending: int
    failed: int

class MttrPointOut(BaseModel):
    week_start: date
    mttr_minutes: float | None

class FragileServiceOut(BaseModel):
    service: ServiceOut
    incident_count: int
    blast_radius_size: int
    fragility_score: float

class RecentBriefOut(BaseModel):
    incident_id: uuid.UUID
    incident_title: str
    brief_id: uuid.UUID
    version: int
    overall_confidence: float | None
    generated_at: datetime | None

class DashboardOut(BaseModel):
    open_incidents: int
    briefs_generated: int
    corpus_size: int
    ingest_health: IngestHealthOut
    mttr_trend: list[MttrPointOut]
    fragile_services: list[FragileServiceOut]
    recent_briefs: list[RecentBriefOut]
```

### `app/services/dashboard_service.py` (new)
`get_dashboard(db, graph_store, *, workspace_id) -> DashboardOut` — six independent
aggregate queries (open incident count, postmortem status counts, brief count, MTTR
per week bucket, recent briefs, fragile-service ranking) run sequentially against the
single request-scoped session (see NFR Performance for why — not `asyncio.gather`),
each scoped by `workspace_id`. Fragile-service ranking computes `blast_radius_
size` via `graph_store.blast_radius` per service — capped to the workspace's services
(bounded by catalog size, not incident volume) — and `incident_count` via one grouped
query across every `IncidentSignal`, not one query per service.

### `app/api/v1/dashboard.py` (new)
`router = APIRouter(prefix="/workspaces/{workspace_id}/dashboard", tags=["dashboard"])`,
one `GET ""` route, `CurrentWorkspaceMember` (read-only for every role, including
viewer — this screen has no write action).

## React Components (Frontend)

### `frontend/src/lib/graph-layout.ts` (new)
Pure function `layeredLayout(nodes, edges) -> Map<serviceId, {x, y, layer}>` — the
cycle-safe longest-path layering from Gap #5, framework-independent so it's testable
without rendering anything.

### `frontend/src/components/service-map/ServiceMapCanvas.tsx` (new)
The SVG itself: nodes sized/colored per FR-01, edges styled per criticality, zoom/pan
via a CSS transform on a `<g>` wrapper (no external pan/zoom library), click handling.

### `frontend/src/components/service-map/ServiceSidePanel.tsx` (new)
Renders on node click: incident history, blast radius list, team contact, runbook
link — FR-02.

### `frontend/src/pages/ServiceMap.tsx` (F9, new)
Fetches graph + teams once, composes the canvas + panel + team/search filter controls.

### `frontend/src/pages/KnowledgeBase.tsx` (F8, new, replaces the `/knowledge-base` stub)
The postmortem table (FR-04) + upload modal (FR-05), reusing the same `useInfiniteQuery`
convention `IncidentList.tsx` established in Phase 9.

### `frontend/src/pages/PostmortemDetail.tsx` (F8 detail, new, contextual route
`/knowledge-base/:id`, same pattern as `IncidentDetail`'s relationship to `IncidentList`)
Renders `redacted_text` with each fact's `[char_start, char_end)` span wrapped in a
highlight `<mark>`, an injection-flagged banner, and the affected-services/failure-mode
chips — FR-06.

### `frontend/src/components/dashboard/*.tsx` (new)
`MetricCard.tsx`, `MttrChart.tsx` (recharts `LineChart`), `FragileServicesTable.tsx`,
`RecentBriefsList.tsx` — composed by `frontend/src/pages/Dashboard.tsx` (F4, new,
replaces the `/dashboard` stub).

### `frontend/src/lib/types.ts` / `lib/api.ts` (extended)
`TeamOut`, `EdgeOut`, `CatalogGraphOut`, `PostmortemServiceLinkOut`, `PostmortemFactOut`,
`DashboardOut` (+ its nested types), `getGraph`, `listTeams`, `getPostmortemDetail`,
`createPostmortem`, `listPostmortems`, `getDashboard`.

## Data Model Changes

None — every field this phase reads already exists (`PostmortemFact.source_chunk_id`,
`PostmortemChunk.char_start/char_end`, `PostmortemService`, `IncidentSignal.
affected_service_ids`, `Incident.opened_at/resolved_at`, `Brief.generated_at`). No new
migration.

## Dependencies

- `recharts` (frontend, new) — FR-08's MTTR line chart. Already anticipated by
  plan.md's tech-stack table; not previously installed since no phase needed a chart
  until now.
- No new backend dependency.

## Edge Cases & Error Handling

- A service with no team (`team_id: null`) — map renders it in a neutral "unassigned"
  color, side panel shows "No team assigned" instead of contact info.
- A service with zero incidents and zero blast radius — still appears in the map;
  excluded from the fragile-services table's top 10 only by naturally sorting last
  (`fragility_score = 0`), not filtered out specially.
- An MTTR week bucket with zero resolved incidents — `mttr_minutes: null`, rendered as
  a gap in the chart line, not a zero (a zero would falsely say "instant resolution").
- A postmortem still `pending`/`processing` when its detail page is opened — renders
  what exists (title, status) and an in-progress state instead of the document view,
  reusing the same "generating" pattern `IncidentDetail` established for briefs.
- Empty corpus / empty catalog / empty incident history anywhere — every list-shaped
  piece of this phase has its own `EmptyState`, matching every prior screen's
  convention; no screen crashes or shows a blank void on a brand-new workspace.
