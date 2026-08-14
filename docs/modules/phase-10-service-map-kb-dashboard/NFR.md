# NFR: Service Map, Knowledge Base, Dashboard

## Performance

- `list_postmortems`'s new `affected_services` resolution is one batched query across
  every postmortem on the current page (`PostmortemService` joined to `Service`,
  grouped by `postmortem_id`), never per-row — same discipline as `_enrich_brief`
  (Phase 9) and blast-radius path resolution (Phase 4).
- `get_dashboard`'s aggregate queries run sequentially against the single request-scoped
  `AsyncSession`, deliberately not `asyncio.gather`'d — this codebase has already hit
  the "concurrent operations on one shared session" failure twice (ADR 0007 §1, ADR
  0008 §4), and every one of these queries is small enough (a handful of small
  aggregates against a single workspace) that sequential execution costs single-digit
  milliseconds total, not worth reintroducing that bug class for.
- Fragile-service ranking calls `graph_store.blast_radius` once per service in the
  workspace, bounded by catalog size (Phase 11's target is 40), not by incident
  volume — a workspace with thousands of incidents doesn't make this query any slower.
- The Service Map's layered layout (Gap #5) is `O(V + E)` — a single longest-path walk
  over the graph, computed once per graph fetch, not per frame; panning/zooming is a
  CSS transform on an already-laid-out `<g>`, not a re-layout.
- Service Map target: no visible stutter at 40 nodes (Phase 11's seed scale), verified
  by a synthetic 40-node/60-edge fixture in a component test asserting layout
  computation completes and every node renders, not a real frame-rate measurement
  (out of reach for `vitest`/`jsdom` — see Testability).

## Security

- Every endpoint this phase adds or extends (`GET .../dashboard`,
  `GET .../postmortems/{id}` detail, `GET .../postmortems` list) is `workspace_id`-
  scoped at the service-layer boundary and readable by every role including viewer —
  none of the three screens has a write action gated any tighter than "must be a
  workspace member," except Knowledge Base's upload/paste modal, which reuses the
  existing owner/responder `require_role` dependency `POST /postmortems` already
  enforces (unchanged this phase).
- `redacted_text`, now returned by the postmortem detail endpoint, is exactly what its
  name says — the same PII/secret-redacted text Phase 5's ingestion pipeline already
  produces and already stores; this phase exposes an existing column, it doesn't
  change what's redacted or when.
- Fact highlighting renders `<mark>`-wrapped spans of `redacted_text` computed from
  server-provided integer offsets, never `dangerouslySetInnerHTML` against anything an
  LLM produced — a malicious/injected postmortem can at worst cause a visually odd
  highlight (e.g. overlapping spans), never script execution.

## Reliability

- `get_postmortem_detail` joins facts to their source chunk rather than resolving each
  fact's offsets through a separate lookup with a "what if it's missing" branch —
  `PostmortemFact.source_chunk_id` is a real, enforced foreign key with `ON DELETE
  CASCADE`, so a fact can never actually outlive its chunk (unlike Phase 9's
  JSONB-stored citations, which have no DB-level guarantee and do need that defensive
  drop). Trusting a real constraint instead of re-implementing its guarantee in
  application code.
- The Service Map's layering algorithm treats a cycle as a back-edge to skip, not an
  error — a catalog graph with a cycle (which Phase 4's own traversal already
  tolerates) still produces a valid, terminating layout, never an infinite loop or a
  500 rendering the map unusable.
- Dashboard aggregates degrade to zero/empty/null individually, never as a whole-
  endpoint failure — a workspace with no postmortems yet returns `corpus_size: 0` and
  an empty `fragile_services`/`recent_briefs`, not an error, the same "new workspace
  looks empty, not broken" bar every other screen already meets.

## Observability

- No new `structlog` events this phase — every code path here is a read (or, for
  Knowledge Base's upload, a call into Phase 5's already-instrumented
  `create_postmortem`). Nothing new happens that a future incident investigation would
  need a fresh log line to reconstruct.

## Testability

- Backend: `test_postmortems.py` (extended) covers the new `affected_services`/
  `facts`/`redacted_text` fields against hand-inserted `PostmortemFact`/
  `PostmortemService` rows (no LLM key configured in this build — see FRD Gap #2, same
  approach `test_enrich_brief.py` used for citations in Phase 9). `test_dashboard_
  service.py` (new) covers each
  aggregate independently against fixtures (a resolved incident inside/outside an MTTR
  bucket boundary, a service with zero vs. nonzero blast radius, an empty workspace).
- Frontend: `graph-layout.test.ts` covers the layered-layout algorithm directly against
  hand-built fixtures — a chain, a diamond, and a cycle — asserting every node gets a
  finite, deterministic position and the algorithm terminates on the cycle fixture
  specifically (a regression test for Gap #5's core claim). Component tests for
  `ServiceMapCanvas`/`ServiceSidePanel`, `KnowledgeBase`'s table/modal, `PostmortemDetail`'s
  highlight rendering, and each dashboard card. E2E (Playwright) seeds a small hand-
  built fixture (a few services/edges/postmortems/incidents via the existing APIs, per
  the PRD's Acceptance Criteria note) and drives all three screens in a real browser:
  opening a service's side panel, uploading a postmortem and watching it index, opening
  its detail page, and loading the dashboard.

## Constraints

- Everything from Phases 1-9's NFRs still applies (async throughout, Pydantic v2 at
  every boundary, `mypy --strict` clean, `workspace_id` filtering on every tenant-
  scoped query, TypeScript strict, React Query for server state).
- No new database tables or migrations — every field this phase reads or returns
  already exists on `Postmortem`/`PostmortemFact`/`PostmortemService`/`PostmortemChunk`/
  `IncidentSignal`/`Incident`/`Brief`.
- One new frontend dependency: `recharts`, for FR-08's MTTR line — already named in
  plan.md's tech-stack table, not previously installed since no earlier phase needed a
  chart. No new backend dependency.
- No paid or external graph-visualization library for the Service Map, per
  Master-Prompt.md's explicit instruction — the layered layout and SVG rendering are
  both hand-rolled.
