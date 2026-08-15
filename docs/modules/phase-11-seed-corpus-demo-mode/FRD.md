# FRD: Seed Corpus & Demo Mode

## Gaps this phase had to resolve

1. **plan.md names two different "12-family" taxonomies, and they aren't the same
   list.** plan.md §12 names 12 *specific failure scenarios* for postmortem content
   ("connection pool exhaustion, retry storm, cache stampede, poison message, cert
   expiry, disk saturation, config rollout, dependency version drift, clock skew,
   thread pool starvation, DNS failover, quota exhaustion") — but Phase 6 already
   built and shipped its own 12-family *classification* taxonomy (`app/services/
   extraction/taxonomy.py`, ADR 0006 §1: `CONFIGURATION_ERROR`, `DEPLOYMENT_FAILURE`,
   `CAPACITY_EXHAUSTION`, `DEPENDENCY_FAILURE`, `NETWORK_CONNECTIVITY`,
   `DATA_CORRUPTION`, `CODE_DEFECT`, `HUMAN_PROCESS_ERROR`, `SECURITY_INCIDENT`,
   `INFRASTRUCTURE_HARDWARE`, `SCALING_LOAD`, `MONITORING_GAP`), which is what the
   `failure_modes`/`postmortem_failure_modes` tables and the correlator's
   failure-mode-overlap scoring actually key against. These are different levels of
   granularity — plan.md's list names *scenarios to write postmortems about*, Phase
   6's list names *categories to classify them into*. Resolved by using plan.md's 12
   scenarios as the content-generation driver (each scenario gets its own vocabulary
   bank and produces roughly 6-7 of the 80 postmortems) and mapping each scenario to
   its closest-fitting Phase 6 family for the `PostmortemFailureMode` link a real
   extraction pass would have produced (e.g. "connection pool exhaustion" →
   `CAPACITY_EXHAUSTION`, "DNS failover" → `NETWORK_CONNECTIVITY`, "config rollout" →
   `CONFIGURATION_ERROR`) — see `app/seed/scenarios.py` for the full mapping table.
2. **No LLM key is configured in this build, but a real extraction pass is what
   populates `postmortem_facts`/`postmortem_services`/`postmortem_failure_modes`.**
   Rather than leaving all 80 seeded postmortems' extraction tables empty (which
   would make Phase 10's Knowledge Base fact-highlighting and affected-services
   chips, and the Dashboard's fragility ranking, look broken for the entire demo),
   the generator emits the "ground truth" extraction output *as a direct byproduct
   of generating the postmortem itself* — since the generator already knows which
   services a postmortem is about, what its root cause is, and what family it
   belongs to (that's literally what it used to compose the document), it writes
   `PostmortemFact`/`PostmortemService`/`PostmortemFailureMode` rows directly, and
   `seed.py` inserts them without ever invoking the real (LLM-dependent) extraction
   agents. This is not a shortcut around Phase 6's design — it's the same principle
   Phase 9's precomputed-brief requirement already establishes (`from_cache=true`,
   `llm_used=false`): synthetic content generated with known ground truth doesn't
   need an LLM to tell it what it already wrote.
3. **Facts need a real `source_chunk_id`, which only exists after real chunking
   runs.** `PostmortemFact.source_chunk_id` is a real, FK-enforced column (Phase 10
   ADR 0010 §3) — a fact can't be written until its chunk exists. Every generated
   postmortem is composed with the exact section headers `chunk.py`'s
   `_SECTION_HEADING_PATTERN` already recognizes (`Summary:`, `Timeline:`,
   `Root Cause:`, `Impact:`, `Remediation:`, `Action Items:`, `Detection:`), each
   section kept under the chunker's 1200-char split threshold so every section maps
   to exactly one chunk. `seed.py` runs the real ingestion pipeline (`redact` →
   `screen` → `chunk` → `embed` → `index_postmortem`, the same functions
   `handle_ingest_postmortem` calls, invoked directly rather than through the job
   queue since seeding is a synchronous script) for every postmortem, then looks up
   each resulting chunk by `section_label` to attach facts to the right real chunk —
   a `Root Cause:`-typed fact always cites the real `Root Cause` chunk, never a
   fabricated id.
4. **"Precomputed" brief doesn't have to mean "fabricated."** Retrieval (vector +
   keyword + graph fusion) and blast-radius computation are both fully deterministic
   and LLM-free — `retriever_node` and `correlator_node` (Phase 8) never call an
   LLM at all. For the 8 incidents that get a precomputed brief, `seed.py` calls
   these two node functions directly (constructing a minimal `TriageState` by hand,
   skipping only the LLM-dependent `normalizer_node`, whose job — resolving alert
   text to candidate service ids — the generator already knows since it authored the
   alert text) against the real seeded, indexed corpus. `matched_postmortems`'
   vector/keyword/graph subscores and `blast_radius` are therefore real computed
   output, not invented numbers. Only the hypothesis statements and runbook steps —
   the parts a real LLM would author — are hand-written by the generator, which
   knows the correct answer because it wrote the underlying postmortems; citations
   on those hypotheses point at real chunk ids from the real retrieval results,
   satisfying the same deterministic citation gate (`citation_check.py`) a real run
   would have to pass.
5. **A demo guest needs to generate briefs, but is provisioned as `VIEWER`.**
   plan.md's Demo Guest description explicitly grants "permission to run new
   incident briefs" on top of read-only access — but `create_demo_guest` (Phase 2)
   provisions every demo guest as `WorkspaceRole.VIEWER`, and brief generation is
   gated `require_role(OWNER, RESPONDER)`. Rather than promoting demo guests to a
   role that would also grant catalog/postmortem/member-management write access (far
   more than the demo is supposed to allow), added a narrow `require_role_or_demo`
   dependency variant used only on the three endpoints this actually applies to
   (`POST /incidents`, `POST .../brief`, `GET .../brief/stream`) — every other
   OwnerOrResponder-gated endpoint (catalog writes, postmortem upload, member
   management, settings) is untouched and still blocks a demo guest exactly like any
   other viewer. Mirrored on the frontend with a `useCanGenerateBrief()` hook
   (`useRequireRole("owner","responder") || user.is_demo`) instead of widening
   `useRequireRole` itself.
6. **Demo-guest brief generation needs its own rate limit, distinct from the
   existing demo-session limiter.** `demo_signup_bucket` (Phase 2) caps how often
   `/auth/demo` can mint a *new* guest per IP — it says nothing about how many briefs
   an *already-minted* guest can generate, and each brief costs real embedding/graph
   compute even with no LLM configured (and would cost a real LLM call once a key is
   added). Added `demo_brief_bucket`, keyed by user id, in the same lightweight
   in-memory `TokenBucket` shape Phase 2 already established — not the project-wide
   rate-limiting pass Phase 14 owns, exactly the same narrow scope precedent
   `demo_signup_bucket` itself set.
7. **The seed workspace and the lazily-created demo workspace must be the same
   row.** `create_demo_guest` already creates a `Workspace(is_demo=True)` on first
   demo login if none exists (Phase 2, written before this phase's seed corpus
   existed to load into it). `seed.py` reuses that exact same "find by `is_demo=
   True`, else create" lookup rather than inventing a second path — whichever runs
   first (an operator's `make seed`, or an unlucky demo visitor who logs in before
   seeding ever ran) creates the row the other then finds and (in seed's case)
   populates.

## Data Model Changes

None — `EvalCase`/`EvalRun`/`EvalCaseResult` already exist from Phase 1 scaffolding
with exactly the shape FR-05 needs; every other table this phase writes to
(`Service`, `Team`, `ServiceEdge`, `Postmortem`, `PostmortemChunk`, `PostmortemFact`,
`PostmortemService`, `PostmortemFailureMode`, `Incident`, `Brief`) already exists.

## Internal Architecture

### `app/seed/scenarios.py` (new)
The 12 plan.md failure scenarios, each with: 2-3 distinct vocabulary sets (phrase
banks for describing the trigger/root cause/remediation in genuinely different
words), a mapped Phase 6 taxonomy family, and a pool of plausible affected-service
*roles* (e.g. "the checkout path's primary datastore") resolved against whichever
concrete seeded service fills that role.

### `app/seed/generate_catalog.py` (new, generator — run once, output committed)
Produces `app/seed/fixtures/catalog.json`: 8 teams, 40 services (tiered, named
realistically — `checkout-api`, `payments-svc`, `postgres-primary`, `redis-cache`,
`auth-service`, `message-bus`, etc.), edges forming a layered dependency graph with 3
services every other tier depends on (the "shared hard dependencies") and 2 services
with exactly one upstream dependent each but no redundancy (the "single points of
failure" — removing either strands a real path with no alternate route). Shape
matches `CatalogImport` (Phase 4) exactly, so loading is a single
`catalog_service.import_catalog` call.

### `app/seed/generate_postmortems.py` (new, generator)
Produces `app/seed/fixtures/postmortems.json`: 80 entries, each `{title, raw_text,
occurred_at, duration_minutes, severity, scenario_key, affected_service_names,
facts: [{fact_type, statement, section_label}], failure_mode}`. `raw_text` is
composed from `scenarios.py`'s phrase banks using a seeded `random.Random(11)` (not
Python's global RNG) so the same script run twice produces byte-identical fixture
output. Dates spread across the last 3 years; roughly a third of documents include a
deliberately wrong initial hypothesis in their `Timeline` section, a partial (not
fully resolved) mitigation, or an incomplete action item, per FR-03.

### `app/seed/generate_incidents.py` (new, generator)
Produces `app/seed/fixtures/incidents.json`: 12 entries `{title, raw_alert_text,
severity, matched_scenario_key, has_precomputed_brief}`, 8 flagged for a precomputed
brief. Alert text deliberately uses a *third* vocabulary variant per scenario (beyond
the postmortems' own 2-3), so matching them back to the right postmortems is a real
test of retrieval generalizing across vocabulary, not a string match.

### `app/seed/generate_eval_cases.py` (new, generator)
Produces `app/seed/fixtures/eval_cases.json`: 20 entries `{name, incident_text,
expected_scenario_key}`. The first 12 reuse the demo incidents' own alert text
(ground truth already known); 8 more are independently generated alert texts against
scenarios already covered by the postmortem corpus, giving Phase 12 a case set larger
than the demo incident list itself.

### `app/seed/seed.py` (new — the only script that touches the database)
`make seed` entrypoint. Idempotent: finds-or-creates the demo workspace, then for
each fixture file, skips any row that already exists (by name for catalog entries, by
title for postmortems/incidents) rather than erroring or duplicating. Sequence:
catalog (via `catalog_service.import_catalog`) → postmortems (via the real ingestion
pipeline functions, called directly, then direct `PostmortemFact`/`PostmortemService`/
`PostmortemFailureMode` inserts per Gap #2/#3) → incidents (via
`incidents_service.create_incident`) → for the 8 flagged incidents, precomputed
briefs (via `retriever_node`/`correlator_node` called directly per Gap #4, plus
hand-authored hypotheses/runbook steps from the fixture) → eval cases (direct
`EvalCase` inserts).

### `app/core/deps.py` (extended)
`require_role_or_demo(*roles: WorkspaceRole)` — same shape as `require_role`, plus an
`current_user.is_demo` escape hatch. Used only where Gap #5 applies.

### `app/api/v1/incidents.py` (extended)
`create_incident`, `generate_brief`, `stream_brief` switch from `OwnerOrResponder` to
a new `OwnerOrResponderOrDemo` alias built on `require_role_or_demo`. `update_incident`
and every other endpoint is untouched.

### `app/services/rate_limit.py` (extended)
`demo_brief_bucket = TokenBucket(capacity=..., refill_seconds=...)`, checked in
`generate_brief`/`stream_brief` only when `current_user.is_demo` is true — a real
owner/responder's brief generation is never rate-limited by this bucket.

### `frontend/src/lib/auth.tsx` (extended)
`useCanGenerateBrief(): boolean` — `useRequireRole("owner","responder") ||
Boolean(user?.is_demo)`. `NewIncident.tsx`/`IncidentDetail.tsx` switch their existing
`canWrite` check for brief-generation actions to this; `AppShell.tsx`'s
`/incidents/new` nav gating switches too, so a demo guest actually sees the nav
entry.

### `frontend/src/components/layout/DemoBanner.tsx` (new)
Renders `"Demo workspace — synthetic data, read-only."` when `user?.is_demo` is true;
mounted once in `AppShell.tsx` above the routed content, visible on every screen for
the duration of a demo session.

## Edge Cases & Error Handling

- `make seed` run a second time against an already-populated demo workspace: every
  insert is preceded by an existence check (service/team by name, postmortem/
  incident by title within the demo workspace); nothing is duplicated, nothing
  raises.
- A demo guest tries an action outside brief generation that a viewer can't do
  (uploading a postmortem, editing the catalog, changing settings): blocked exactly
  like any other viewer, both by the existing frontend gating and the unmodified
  backend `require_role` checks on those endpoints.
- A demo guest exhausts `demo_brief_bucket`: `POST .../brief` and the SSE stream both
  return the same `RateLimitedError` shape `demo_signup_bucket` already produces —
  no new error type.
