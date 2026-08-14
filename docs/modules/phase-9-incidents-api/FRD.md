# FRD: Incidents API + The Money Screen

## Gaps this phase had to resolve

1. **`char_start`/`char_end` are offsets into the postmortem's *full document text*,
   not the cited chunk's own content** (confirmed by reading `chunk.py`: a chunk's
   `content` literally *is* `redacted_text[char_start:char_end]`). Master-Prompt.md's
   "highlighted (use `char_start`/`char_end`)" language assumes a full-document view to
   scroll and highlight within — that's F8 (Knowledge Base), Phase 10, out of scope
   here. This phase's citation chips instead show the cited chunk's own content inline
   (which *is* the grounding excerpt, already exactly as specific as "the highlighted
   passage" would be) — `char_start`/`char_end` are still resolved and returned now so
   Phase 10 can wire the real deep-link without a second API change.
2. **Phase 8's internal schemas (`Citation`, `CandidateMatch`, `Hypothesis`,
   `RunbookStepDraft`) carry only ids, not the human-readable content a UI needs**
   (postmortem titles, chunk text, severity). Rather than changing Phase 8's types
   (used inside the graph and persisted as JSONB) or duplicating logic to reshape them
   client-side, this phase defines its own response-only schemas
   (`app/schemas/incident_api.py`) that enrich Phase 8's ids with batched lookups at
   read time — the graph's internal contract and the HTTP API's contract are
   deliberately different layers.
3. **Native browser `EventSource` cannot send the `Authorization: Bearer` header this
   app's entire auth model relies on** (Phase 2's JWT-in-header pattern, not
   cookie-based API auth). Rather than inventing a query-string token (a real
   credential leak risk — URLs get logged) or switching this app's whole auth model,
   F5/F6 consume the SSE stream via `fetch()` + a hand-rolled reader
   (`frontend/src/lib/sse.ts`), which supports arbitrary headers exactly like every
   other API call this app already makes.
4. **Both `POST .../brief` (FR-04) and `GET .../brief/stream` (FR-05) run the same
   underlying graph invocation** — factored so both call through the same
   `incidents_service` construction of `(graph_store, router, checkpointer, graph)`,
   differing only in whether they `await graph.ainvoke(...)` (blocking, FR-04) or
   `async for event in stream_graph_events(...)` (FR-05). Each request gets its own
   freshly compiled graph and its own checkpointer connection — no app-level singleton,
   consistent with Phase 8's own documented restraint (ADR 0008 §6) not to hold a
   checkpointer open with no request behind it.

## API Endpoints (Backend — FastAPI)

All under `router = APIRouter(prefix="/workspaces/{workspace_id}/incidents",
tags=["incidents"])`. `OwnerOrResponder = Depends(require_role(OWNER, RESPONDER))`,
mirroring `postmortems.py`'s exact pattern.

### `POST ""` — create incident
- Auth: `OwnerOrResponder`.
- Body: `IncidentCreate{title, raw_alert_text, external_ref?, severity?}`.
- `201` → `IncidentOut`. `opened_by = current_user.id`, `opened_at = now()`,
  `status = OPEN`.

### `GET ""` — list incidents
- Auth: any member.
- Query: `status?`, `severity?`, `service_id?` (matches if *any* of the incident's
  `incident_signals` rows has `affected_service_ids @> ARRAY[service_id]` — Postgres
  array containment via SQLAlchemy's `.contains([service_id])`; matching any historical
  signal, not only the latest, is a deliberate simplification — see NFR), `cursor?`,
  `limit? = 20`.
- `200` → `CursorPage[IncidentOut]`.

### `GET "/{incident_id}"` — incident detail
- Auth: any member. `404` if not found or wrong workspace (existing `get_incident`
  pattern, matching `postmortem_service.get_postmortem`).
- `200` → `IncidentOut`.

### `PATCH "/{incident_id}"` — update incident
- Auth: `OwnerOrResponder`.
- Body: `IncidentUpdate{status?, title?}`. Setting `status` to `resolved` or
  `false_positive` sets `resolved_at = now()` if not already set; setting it back to
  `open`/`mitigated` does **not** clear `resolved_at` (an incident's resolution history
  isn't erased by reopening it — a deliberate choice, not an oversight).
- `200` → `IncidentOut`.

### `POST "/{incident_id}/brief"` — generate a brief (blocking)
- Auth: `OwnerOrResponder`.
- Runs `incidents_service.generate_brief` to completion, `200` → `BriefOut`.

### `GET "/{incident_id}/brief/stream"` — generate a brief (SSE)
- Auth: `OwnerOrResponder` (same write-cost action as FR-04, just observed live).
- `EventSourceResponse` wrapping `incidents_service.stream_brief_generation`, each
  yielded `{"type": ..., ...}` dict from Phase 8's `stream_graph_events` translated to
  `{"event": type, "data": json.dumps(payload)}` for `ServerSentEvent`.

### `GET "/{incident_id}/briefs"` — list brief versions
- Auth: any member.
- `200` → `list[BriefOut]`, newest version first.

### `POST "/{incident_id}/brief/{brief_id}/feedback"` — record feedback
- Auth: any member.
- Body: `BriefFeedbackCreate{verdict, correct_postmortem_id?, note?}`.
- `201` → `BriefFeedbackOut`.

All error responses use the existing `{"error": {"code","message","detail"}}` envelope.

## Internal Architecture

### `app/schemas/incident_api.py` (new)

```python
class IncidentCreate(BaseModel):
    title: str
    raw_alert_text: str
    external_ref: str | None = None
    severity: Severity | None = None

class IncidentUpdate(BaseModel):
    status: IncidentStatus | None = None
    title: str | None = None

class IncidentOut(BaseModel):
    id: UUID; workspace_id: UUID; external_ref: str | None; title: str
    raw_alert_text: str; severity: Severity | None; status: IncidentStatus
    opened_by: UUID | None; opened_at: datetime; resolved_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}

class CitationOut(BaseModel):
    chunk_id: UUID; postmortem_id: UUID; postmortem_title: str
    quote: str | None; content: str; char_start: int; char_end: int

class HypothesisOut(BaseModel):
    statement: str; confidence: float; citations: list[CitationOut]

class RunbookStepOut(BaseModel):
    step: str; source_postmortem_id: UUID | None; citation: CitationOut | None

class MatchedPostmortemOut(BaseModel):
    postmortem: PostmortemOut  # reused from app/schemas/postmortem.py
    vector_score: float; keyword_score: float; graph_score: float
    failure_mode_overlap: float; recency: float; overall_score: float; rank: int

class BriefOut(BaseModel):
    id: UUID; incident_id: UUID; version: int
    hypotheses: list[HypothesisOut]
    matched_postmortems: list[MatchedPostmortemOut]
    blast_radius: BlastRadius  # reused from app/services/graph_store.py
    runbook_steps: list[RunbookStepOut]
    citations: list[CitationOut]
    overall_confidence: float | None; correction_passes: int
    llm_used: bool; from_cache: bool; generated_at: datetime | None

class BriefFeedbackCreate(BaseModel):
    verdict: FeedbackVerdict
    correct_postmortem_id: UUID | None = None
    note: str | None = None

class BriefFeedbackOut(BaseModel):
    id: UUID; brief_id: UUID; user_id: UUID | None; verdict: FeedbackVerdict
    correct_postmortem_id: UUID | None; note: str | None; created_at: datetime
    model_config = {"from_attributes": True}
```

### `app/services/incidents_service.py` (new)

- `create_incident`, `list_incidents` (cursor pattern identical to
  `postmortem_service.list_postmortems`), `get_incident`, `update_incident` — plain
  CRUD, no surprises.
- `async def generate_brief(db, graph_store, router, *, incident: Incident) -> BriefOut`
  — starts an `AgentRun` row, opens `AsyncPostgresSaver.from_conn_string(
  checkpointer_conn_string(settings))`, `await saver.setup()`, `build_graph(db,
  graph_store, router, checkpointer=saver)`, `initial_state(incident_id=incident.id,
  workspace_id=incident.workspace_id, raw_text=incident.raw_alert_text)`,
  `await graph.ainvoke(state, config={"configurable": {"thread_id":
  str(incident.id)}})`. Marks the `AgentRun` `done`/`error` with `finished_at`, then
  returns the persisted brief (already written by `briefer_node`) through
  `_enrich_brief`.
- `async def stream_brief_generation(db, graph_store, router, *, incident: Incident) ->
  AsyncIterator[dict[str, object]]` — identical setup, `async for event in
  stream_graph_events(graph, state, thread_id=str(incident.id), run_id=run.id): yield
  event`, updating the same `AgentRun` row to `done`/`error` when the loop ends
  (`try`/`finally` around the `async for`, so a client disconnect mid-stream still
  marks the run instead of leaving it `running` forever).
- `async def list_briefs(db, *, incident_id) -> list[BriefOut]` — raw rows through
  `_enrich_brief`.
- `async def _enrich_brief(db, brief: Brief) -> BriefOut` — the FRD Gap #2 resolver:
  collects every `chunk_id` referenced across `citations`/`hypotheses`/`runbook_steps`
  and every `postmortem_id` referenced across `citations`/`matched_postmortems` into
  two sets, resolves both with **one batched query each**
  (`select(PostmortemChunk).where(PostmortemChunk.id.in_(chunk_ids))`,
  `select(Postmortem).where(Postmortem.id.in_(postmortem_ids))` — never N+1), then
  reassembles the JSONB-parsed Phase 8 types into the enriched `*Out` schemas above.
- `async def record_feedback(db, *, brief_id, user_id, payload) -> BriefFeedbackOut`.

### `app/api/v1/incidents.py` (new)

Thin FastAPI router matching the Endpoints section exactly; constructs
`PostgresGraphStore(db)` and `build_router(get_settings())` once per request (matching
every existing job handler's pattern), passes them into `incidents_service`.

### `app/agents/build_graph.py` (no change — already exposes
`checkpointer_conn_string`/`build_graph` for this phase to call)

## React Components (Frontend)

### `frontend/src/lib/sse.ts` (new)

```typescript
export async function streamSse(
  url: string, init: RequestInit, onEvent: (evt: { event: string; data: string }) => void
): Promise<void>
```
Reads the fetch response body via `getReader()`, buffers on `\n\n`-delimited SSE
frames, parses `event:`/`data:` lines per frame — see FRD Gap #3 for why this exists
instead of native `EventSource`.

### `frontend/src/pages/NewIncident.tsx` (F5, replaces the `/incidents/new` stub)

Textarea + 3 sample-alert buttons (hardcoded realistic examples, matching plan.md's
demo framing) → `POST /incidents` → immediately opens the SSE stream for that new
incident's id via `streamSse` → renders `<AgentPipelineTrace>` (below) live → on the
`done` event, fetches `GET .../briefs` and renders `<BriefView>` for the newest one.

### `frontend/src/pages/IncidentDetail.tsx` (F6, new route `/incidents/:id`, not a
sidebar entry per `screens.ts`'s existing comment)

Fetches the incident + its briefs; renders `<BriefView>` for the newest brief (or an
empty state if none exist yet, with a "Generate brief" button reusing the same SSE flow
as F5 inline). A "Regenerate" action (owner/responder only) re-runs the same flow.

### `frontend/src/pages/IncidentList.tsx` (F7, replaces the `/incidents` stub)

Filter controls (status/severity/service — service filter populated from
`GET /catalog/services`, Phase 4), a paginated row list, each row linking to
`/incidents/:id`.

### `frontend/src/components/incidents/AgentPipelineTrace.tsx` (new, shared by F5/F6)

Six node chips (`normalizer → retriever → correlator → analyst → critic → briefer`)
each in `queued | running | done` state with elapsed ms once running, driven entirely
by the `node_start`/`node_end` events passed in as props — a `retry` event shows a
visible "refining retrieval" label and resets the four downstream nodes
(`correlator`/`analyst`/`critic`/`briefer`, plus `retriever` itself) back to `queued`.

### `frontend/src/components/incidents/BriefView.tsx` (new, shared by F5/F6)

Renders `BriefOut`: hypotheses with `ConfidenceBadge` (already exists) and citation
chips (click → inline excerpt panel using the citation's own `content`, per Gap #1);
matched postmortems with a small 5-bar subscore breakdown per candidate; a blast radius
panel (ordered `BlastRadiusEntry` list); runbook steps with source attribution; a
feedback control (helpful/partially/unhelpful + optional "the correct match was ___"
naming one of the matched postmortems); badges for `from_cache`, `llm_used === false`,
and `correction_passes > 0`.

### `frontend/src/lib/types.ts` / `lib/api.ts` (extended)

Types hand-kept in sync with `app/schemas/incident_api.py`, matching this file's
existing no-codegen convention. `api.ts` gains `createIncident`, `listIncidents`,
`getIncident`, `updateIncident`, `generateBrief`, `streamBrief` (thin wrapper over
`lib/sse.ts` typed to the specific SSE event shapes), `listBriefs`, `submitFeedback`.

## Data Model Changes

None — every table this phase writes to (`incidents`, `incident_signals`, `briefs`,
`brief_feedback`, `agent_runs`, `agent_run_steps`) already existed since Phase 1; Phase
8 already writes to `incident_signals`/`briefs`/`agent_run_steps`. This phase adds the
first writer for `brief_feedback` and the first *reader* for all of them via a real API.

## Dependencies

Phase 4's `PostgresGraphStore`, Phase 6's `build_router`, Phase 8's `build_graph`/
`checkpointer_conn_string`/`initial_state`/`stream_graph_events`/`IncidentBrief`-family
schemas. Phase 10's F8 will eventually consume `CitationOut.char_start`/`char_end` for
real in-document highlighting. Phase 12's evaluation harness will read
`brief_feedback.correct_postmortem_id`.

## Sequence Flows

**Live brief generation (F5)**
1. `POST /incidents` → `Incident` row created, `status=open`.
2. Frontend opens `GET /incidents/{id}/brief/stream` via `streamSse`.
3. Backend starts an `AgentRun`, builds a fresh checkpointer + graph, streams
   `node_start`/`node_end` per node as `stream_graph_events` yields them; a forced
   retry emits a `retry` event before `retriever`'s second `node_start`.
4. `done` event (with `brief_id`) → frontend fetches `GET .../briefs`, renders the
   newest.
5. If `LLMUnavailable` was raised anywhere, the run still completes — `error` is never
   emitted for this case (Phase 8's degradation contract), only `done`, with
   `llm_used=false` visible on the rendered brief via its badge.

**Blocking generation (API-only caller, no live viewer)**
1. `POST /incidents/{id}/brief` → same underlying `generate_brief` call, `200` →
   `BriefOut` once the whole run completes.

## Edge Cases & Error Handling

| Edge case | Handling |
|---|---|
| Brief generation requested for an incident with no prior corpus data | Deterministic nodes still run cleanly (empty `matched_postmortems`/`blast_radius`), matching Phase 7/8's established "empty is not an error" convention |
| Client disconnects mid-SSE-stream | The `AgentRun` row is still marked `done`/`error` via the `finally` block in `stream_brief_generation`, even though nothing is listening |
| A citation's `chunk_id` no longer resolves (postmortem deleted between generation and read) | Dropped from the enriched response rather than raising — `_enrich_brief` only includes citations it could actually resolve |
| `service_id` filter matches an incident via an old signal, not the current one | Accepted simplification (FRD Gap items) — the alternative (latest-signal-only) needs a windowed subquery for a filter Master-Prompt.md doesn't specify precisely enough to justify the complexity |
| Non-member queries another workspace's incident | `404`, via the existing `get_current_workspace` dependency |
| Viewer attempts `POST`/`PATCH` on incidents or brief generation | `403`, via `require_role(OWNER, RESPONDER)` |
