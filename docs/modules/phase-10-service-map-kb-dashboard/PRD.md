# PRD: Service Map, Knowledge Base, Dashboard

## Problem

By Phase 9 the platform can ingest postmortems, hold a service dependency graph, and
generate incident briefs — but none of that is visible except through the two screens
that already exist (Search, Incidents). There is no way to *see* the dependency
topology a blast-radius score is describing, no way to browse or audit the postmortem
corpus as a corpus rather than one document at a time, and no single screen answering
"how is this workspace doing right now." All three screens this phase builds are
read-oriented views over data that already exists (Phase 4's catalog/graph, Phase 5's
postmortems, Phase 9's incidents/briefs) — this phase is about visibility, not new
domain logic.

## Actors

- **Owner / Responder** — full read access to all three screens; can additionally
  upload/paste new postmortems from the Knowledge Base.
- **Viewer** — full read access to all three screens; the Knowledge Base's
  upload/paste entry point is hidden and gated, matching the write-action pattern
  already established for `/incidents/new` (Phase 9) and `/settings` (Phase 3).

## Functional Requirements

**Service Map (F9)**

- FR-01: Render every workspace service as a node and every dependency as an edge, via
  a custom SVG layout — no charting/graph library. Node size encodes tier (`TIER_1`
  largest), edge style encodes criticality (`hard` solid, `soft` dashed), node color
  encodes owning team.
- FR-02: Clicking a node opens a side panel showing: that service's incident history,
  its blast radius (highlighted in red on the map itself), its owning team's contact
  info, and its runbook link (if set).
- FR-03: Zoom, pan, filter by team, and search by name. Must render 40 nodes (Phase
  11's seed corpus target) without visible stutter.

**Knowledge Base (F8)**

- FR-04: A postmortem table showing status, severity, date, and affected services,
  paginated, filterable by status.
- FR-05: A paste/upload modal that creates a postmortem and shows its ingest status
  live until it reaches `indexed` or `failed`.
- FR-06: A detail view rendering the full redacted document with extracted facts
  highlighted inline at their source location, and a visible warning banner when
  `injection_flagged` is true.

**Dashboard (F4)**

- FR-07: Metric cards — open incidents, briefs generated, corpus size, ingest health.
- FR-08: An MTTR trend line chart (recharts) over recent weeks.
- FR-09: A most-fragile-services table, ranked by a combination of how often a service
  is implicated in an incident and how wide its blast radius is.
- FR-10: A recent-briefs list, workspace-wide (not scoped to one incident the way
  Phase 9's `IncidentDetail` is).

## User Stories

- As a responder investigating an incident, I want to see a service's dependency
  neighborhood on a map so I understand what else might be affected before I finish
  reading the brief.
- As an owner reviewing the corpus, I want to browse every postmortem in one table and
  open any one of them to see exactly what was extracted from it and where.
- As anyone opening the app in the morning, I want one screen that tells me whether
  things are currently okay without opening the incident list.

## Out of Scope

- A physics-based force-directed simulation — Master-Prompt.md says
  "layered/force layout"; this phase implements a deterministic layered layout (see
  FRD Gap #3 for why), not a randomized physics simulation, since the acceptance bar
  is "handles 40 nodes without stutter," not "looks organic."
- Exact-substring fact highlighting — facts are highlighted at their *source chunk's*
  location, the same chunk-level granularity Phase 9's citations already established
  (FRD Gap #1 there), not a second, finer-grained offset system.
- CSV/PDF export of any of the three screens.
- Real-time collaborative viewing (multiple users' cursors, live updates on someone
  else's edit) — every screen here is a snapshot fetched on load / on demand.

## Acceptance Criteria

Master-Prompt.md's phase checkpoint: **all three screens work against seeded data and
are usable on a laptop screen without horizontal scrolling.** Phase 11 (the real 40/80/
12-item seed corpus) doesn't exist yet, so this phase's own verification — same
precedent as every backend-only phase before Phase 11 — creates small hand-built
fixtures directly via the existing APIs (a handful of services/edges/postmortems/
incidents), not the full seeded corpus. Phase 11 is expected to be the first phase that
actually exercises these three screens at their target scale (40 services, 80
postmortems); this phase's own e2e coverage proves the screens are correct, not that
they're fast at 40 nodes specifically (verified instead by a synthetic node-count
check — see NFR Performance).
