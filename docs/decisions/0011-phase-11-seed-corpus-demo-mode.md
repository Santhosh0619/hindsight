# ADR 0011: Seed Corpus & Demo Mode — Ground Truth Without an LLM, and Two RBAC Scoping Bugs

## 1. Two different "12-family" lists, resolved with an explicit mapping table

**Context.** plan.md §12 names 12 specific *content* scenarios for the seed corpus
(connection pool exhaustion, retry storm, cache stampede, poison message, cert expiry,
disk saturation, config rollout, dependency version drift, clock skew, thread pool
starvation, DNS failover, quota exhaustion). Phase 6 already shipped its own, different
12-family *classification* taxonomy (`FailureModeFamily` in
`app/services/extraction/taxonomy.py`, ADR 0006 §1) that every postmortem's
`PostmortemFailureMode` row has to point at. Both are legitimately "the 12 families" in
their own document, and neither references the other.

**Decision.** Treated plan.md's list as content-generation scenarios and Phase 6's list
as the fixed classification vocabulary, connected by an explicit `Scenario.family`
field in `app/seed/scenarios.py` — one mapping table, not a third taxonomy invented to
paper over the collision. Inventing a new list would have been simpler in the moment
but would leave the demo corpus using a vocabulary the rest of the app doesn't
recognize.

## 2. Ground-truth extraction instead of the real (unconfigured) LLM agents

**Context.** No LLM key is configured for this build (a standing choice since Phase 6).
The Knowledge Base features Phase 6/9/10 already shipped — fact highlighting, service
links, failure-mode tags — all depend on `postmortem_facts`/`postmortem_services`/
`postmortem_failure_modes` being populated, which normally only happens through the
real extraction agents.

**Decision.** Since the generator scripts author every postmortem's content, they
already know its ground truth as a byproduct of generation. `generate_postmortems.py`
emits facts/service-links/failure-mode as explicit fields on each fixture entry;
`seed.py` inserts them directly, never invoking the extraction agents. `llm_used` and
`from_cache` stay accurate throughout — this isn't pretending an LLM ran, it's
recognizing that a hand-authored corpus's ground truth doesn't need to be
re-discovered by the same pipeline that would need to discover it from a real,
opaque incident report.

## 3. "Precomputed" briefs call the real retriever and correlator, not a script

**Context.** 8 of the 12 demo incidents ship with a brief already attached, so a demo
visitor doesn't have to wait for one to generate before seeing the product's payoff.
The easy way to build that is to hand-write plausible-looking JSON. The honest way is
harder: `retriever_node` and `correlator_node` (Phase 8) are pure and deterministic —
no LLM call in either — which means they can be invoked directly outside the full
`StateGraph` machinery.

**Decision.** `seed.py` hand-builds a minimal `TriageState` (skipping only the
LLM-dependent `normalizer_node`, whose output the generator already knows since it
authored the alert text) and calls both real node functions against the real seeded,
indexed corpus. `matched_postmortems` scores and `blast_radius` are therefore genuinely
computed, not invented — verified live by inspecting all 8 briefs' top-ranked match:
6/8 land on the exact right scenario, the other 2 rank it #2 or #5–6 behind a closely
related scenario in the same broad failure family, a real near-miss from real hybrid
retrieval. Only the hypothesis prose and runbook steps (the parts an LLM would
normally author) are hand-derived from the matched postmortem's own facts, citing real
chunk ids that would pass the same grounding check a live citation gate enforces. See
FRD Gap #4.

## 4. Two independent copies of the same RBAC scoping bug, caught by code review

**Context.** A demo guest is provisioned as VIEWER (Phase 2) but the demo experience
needs them to generate briefs, so `require_role_or_demo` (backend) and
`useCanGenerateBrief`/`DemoBanner` (frontend) each carve out an exception for
`is_demo`. The first version of both checked only the account-wide flag — a demo
guest's `is_demo` never changes, no matter which workspace they're looking at.

**Decision.** A demo guest can join a real workspace via invite code like anyone else
and be demoted to viewer there by its owner, expecting that to actually restrict them.
Backend code review caught that the unscoped check would let a demo guest keep write
access in that real workspace, since `require_role_or_demo` never checked *which*
workspace was being accessed — fixed by also requiring `workspace.is_demo` on the
membership's own workspace. A second, separate review pass on the frontend then caught
the identical bug shape in `useCanGenerateBrief`/`DemoBanner`, which had no way to
even express the distinction until `MembershipOut` grew a `workspace_is_demo` field.
Both fixes shipped with a regression test that exercises the exact scenario (join,
demote, still denied) rather than re-asserting the same case the original bug already
passed. The frontend fix was then itself flagged for implementing the same predicate
twice in two hooks — extracted into one `useIsDemoWorkspace()` so a future change
can't update one call site and miss the other, mirroring how the backend already
consolidates the same check into one dependency.

## 5. Idempotency requires one commit per fixture entry, not one per row-group

**Context.** `seed.py`'s idempotency (FR-06) works by checking whether a title already
exists before inserting. The first version of `_seed_postmortems` and `_seed_incidents`
each spanned multiple `db.commit()` calls per fixture entry — ingest the postmortem,
commit; add its facts/services/failure-mode, commit again. A crash between those two
commits leaves a postmortem row whose title a rerun recognizes as "already seeded,"
permanently skipping the facts it should have gotten.

**Decision.** Both functions now do exactly one commit per fixture entry, after every
row that entry produces has been added to the session — `_ingest_one` flushes instead
of committing internally, and `_precompute_brief` no longer commits its own `Brief`
row, so a crash mid-entry rolls the whole entry back instead of leaving a row a rerun
would trust. Caught by code review reasoning through the exact failure window, not by
any test — the happy-path idempotency test (run twice, same counts) can't distinguish
"never partially failed" from "correctly recovers from a partial failure," since it
never induces one.

## 6. A generator bug that only bites on a resumed run, not a fresh one

**Context.** `generate_postmortems.py` picks a service by cycling
`candidates[i % len(candidates)]` through a scenario's role-matched services. When a
scenario's postmortem count exceeds its candidate pool (`cache_stampede`: 3 cache-role
services, 7 postmortems), the same `(scenario, service)` pair recurs, and the title —
`f"{service}: {scenario_key}"` — has no other input, so two distinct postmortems
land on the identical title.

**Decision.** On a from-scratch run this is invisible: `seed.py`'s existence check
starts with an empty title set, so both rows insert regardless of the collision. It
only surfaces on a resumed run (after a partial failure, or an operator re-running
`make seed`), where `postmortem_id_by_title` — built from `SELECT title, id`, one row
per unique title — silently collapses the duplicates down to a single id, corrupting
`ids_by_scenario` for every incident/eval-case created in that same resumed run.
`_title_for` now takes an occurrence count and appends `" (N)"` past the first
occurrence of a pair; `postmortems.json` was regenerated (80/80 unique titles,
confirmed byte-identical across two regenerations) and the already-seeded demo
workspace reset and reseeded from scratch on the fixed fixture.

## 7. Removed a stale Phase 3 stub instead of leaving it for later

**Context.** Onboarding's "Seed with demo data" card has been a disabled button
reading "Coming in Phase 11" since Phase 3, on the assumption that this phase would
let a brand-new signup seed *their own* workspace with synthetic data on demand.
Phase 11's actual scope — decided in this phase's own PRD before any code — is one
shared demo workspace populated once via `make seed`, not a per-signup feature; that
assumption never matched what got built.

**Decision.** Removed the card rather than leave the stale placeholder in place. A
permanently disabled button citing an internal phase number reads as an abandoned
feature to anyone evaluating the finished app, which is a worse outcome for a
portfolio-facing project than a slightly simpler Onboarding screen. `Start empty`'s
copy now points anyone curious toward the real "Try the live demo" flow instead.
