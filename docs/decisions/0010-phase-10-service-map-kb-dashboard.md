# ADR 0010: Service Map, Knowledge Base, Dashboard — Layout, Fragility, and a Docker Bind-Mount Gap

## 1. A deterministic layered layout instead of a force-directed simulation

**Context.** Master-Prompt.md says the Service Map needs a "layered/force layout," and
names "no paid library" as a constraint. A real force-directed layout (repulsion +
spring edges, iterated to a stable configuration) is the more visually organic choice,
but it's non-deterministic between renders, expensive to keep smooth at 40 nodes
without an actual physics library (out of scope), and hard to test — asserting on node
positions from a physics simulation is either flaky or vacuous.

**Decision.** Built a hand-rolled layered layout instead: each service's layer is the
length of its longest acyclic path from a root, computed by repeatedly placing the
frontier node with the fewest still-unplaced predecessors (ties broken by name). This
makes topological progress every iteration regardless of how many cycles the graph
contains — a node's remaining unplaced predecessors are simply treated as back-edges
once it's chosen, never revisited — so the algorithm always terminates in exactly
`|nodes|` steps. Fully deterministic given the same graph and directly unit-testable
(`graph-layout.test.ts` covers a chain, a diamond, a cycle, and a 40-node/60-edge
fixture at Phase 11's target scale) without rendering anything. See FRD Gap #5.

## 2. Fragility score: incident count weighted by blast radius, defined precisely

**Context.** Master-Prompt.md's dashboard spec names "most-fragile services... ranked
by incident count weighted by blast radius" without saying how to combine the two
numbers.

**Decision.** `fragility_score = incident_count × (1 + blast_radius_size)`.
`incident_count` counts distinct incidents whose `IncidentSignal.affected_service_ids`
includes the service, resolved with a single `unnest`-based grouped query across every
signal in the workspace — not one query per service. The `+ 1` means a service with
zero downstream dependencies still scores by its raw incident count rather than
collapsing the whole product to zero: a single-node service that keeps breaking is
still fragile, just not *contagious*, and the formula shouldn't erase that. See FRD
Gap #4.

## 3. Trusting a real foreign key instead of re-implementing its guarantee

**Context.** The first draft of `get_postmortem_detail` resolved each fact's highlight
offsets through a lookup dict keyed by `source_chunk_id`, with a branch dropping any
fact whose chunk "no longer resolves" — mirroring Phase 9's `_enrich_brief`, which
genuinely needs that branch because citations are stored as JSONB with no database-
level guarantee. Writing the test for that exact scenario (`PostmortemFact` inserted
with a random `source_chunk_id`) failed immediately: `PostmortemFact.source_chunk_id`
is a real foreign key with `ON DELETE CASCADE`. A fact can never actually outlive its
chunk — the row would be deleted along with it.

**Decision.** Removed the defensive branch and joined `PostmortemFact` straight to
`PostmortemChunk` in one query instead. CLAUDE.md's own rule — don't add handling for
scenarios that can't happen — applies literally here: the dangling-reference case
Phase 9 has to guard against for JSONB doesn't exist for a real, enforced FK. Caught
only by trying to write the test the code's own comment claimed was covered, not by
reading the code in isolation.

## 4. Dashboard aggregates run sequentially, not gathered — the third time this
   constraint has mattered

**Context.** The first draft of the FRD described `get_dashboard`'s five/six aggregate
queries as running "concurrently where they touch disjoint tables." They don't share
a session-per-branch the way Phase 7's retrieval fan-out does (ADR 0007 §1) — they all
share the one request-scoped `AsyncSession`, which cannot run concurrent operations
regardless of whether the queries touch different tables.

**Decision.** Every aggregate awaits in sequence. Given each query is a small,
single-workspace aggregate, the real cost of serializing them is single-digit
milliseconds — not worth reintroducing the exact failure class ADR 0007 §1 and ADR
0008 §4 already hit and fixed. Caught while implementing, before ever running the
code, specifically because writing that FRD sentence out loud triggered the memory of
having fixed this same mistake twice before — the NFR was corrected in the same
session and REVIEW-BE independently confirmed the shipped code matches the corrected
NFR, not the stale FRD wording (which was then also fixed).

## 5. A Docker bind-mount gap: `package.json` isn't mounted, only `src/` and `public/`

**Context.** Adding `recharts` via `docker compose exec web npm install recharts`
updated the package inside the container correctly, but `git status` on the host
showed no changes to `frontend/package.json` or `package-lock.json` at all.
`docker-compose.yml`'s `web` service only bind-mounts `./frontend/src` and
`./frontend/public` — `package.json`, `package-lock.json`, and `node_modules` all live
solely inside the image's own filesystem, baked in at build time. `npm install` run
inside a already-running container correctly mutates the container's copy, which is
simply a different filesystem than the host's.

**Decision.** Used `docker cp` to copy the container's updated `package.json`/
`package-lock.json` back to the host after installing, which is what actually made the
dependency change committable. This is a one-off manual step for this session, not a
process change — the alternative (bind-mounting `package.json` too) would let a stale
host copy silently diverge from what's actually built into the image between
rebuilds, which is worse. Worth knowing for the next phase that adds a dependency:
`npm install` inside the running dev container is real, but isn't visible to git until
copied out.

## 6. REVIEW-FE's findings, and what they say about the review discipline itself

**Context.** Both Knowledge Base and Dashboard got real loading/error/empty-state
handling and page-level tests on the first implementation pass, closely following the
pattern IncidentList/IncidentDetail already established in Phase 9. Service Map didn't:
its blast-radius/incident-history sub-queries only branched on loading vs. success, and
the page itself had no error branch at all — a failed catalog fetch would have rendered
identically to a genuinely empty, unonboarded workspace, with no way to tell them apart
and no retry affordance. There was also no `ServiceMap.test.tsx` at all going into
review.

**Decision.** Fixed by adding the missing error branches (page-level and, separately,
inside `ServiceSidePanel`'s two independent sub-queries) and the missing test file,
verified by re-running REVIEW-FE rather than trusting the fix — the re-review
independently re-read the corrected code, ran the affected tests itself (18/18), and
confirmed a real `tsc --noEmit` pass before approving. The gap wasn't a subtle bug; it
was inconsistency between two pages built the same phase, which is exactly the class
of thing a same-session review catches better than solo implementation does.
