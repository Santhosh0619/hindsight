# ADR 0004: Service Catalog & Graph Traversal — CTE Design and Bugs Found

## 1. Recursive CTE behind a `GraphStore` protocol, not a graph database

**Context.** plan.md §7 commits to one Postgres database with no dedicated graph store
(no Neo4j). This phase is the first that actually needs graph traversal — blast radius,
upstream/downstream reachability — so it's the first real test of that decision.

**Decision.** `app/services/graph_store.py` defines a `GraphStore` Protocol
(`upstream`/`downstream`/`neighborhood`/`blast_radius`/`shortest_path`), and
`app/services/postgres_graph_store.py` implements it with a single recursive CTE
(`_reach_cte`), parameterized by direction (`reverse=True` swaps which side of
`service_edges` is followed, giving upstream instead of downstream for free). Cycle
safety comes from carrying the visited-path array and rejecting a next hop already in
it (`NOT (e.to_service_id = ANY(r.path))`) — a cycle can only grow `reach` to at most
one row per service in the workspace, so termination is guaranteed without a depth cap.
Diamond correctness comes from `DISTINCT ON (service_id) ... ORDER BY depth ASC`,
keeping only the shortest path to each reached service. Because it's just a Protocol, a
future Neo4j-backed implementation (if the graph ever outgrows what a CTE handles well)
can satisfy the same interface without touching any caller.

## 2. `ServiceTier` is the one enum whose Postgres label is the member name, not its value

**Context.** `ServiceTier(int, enum.Enum)` stores `TIER_1 = 1`, `TIER_2 = 2`,
`TIER_3 = 3`. Every other enum in this codebase (`EdgeKind`, `EdgeCriticality`, etc.)
uses `Enum(..., values_callable=enum_values)` so its Postgres column stores the
member's *value* (`"calls"`, `"hard"`). `ServiceTier`'s column
(`app/models/catalog.py`) is declared as plain `Enum(ServiceTier, name="service_tier")`
with no `values_callable` — a deliberate Phase 1 choice, since the member names
(`TIER_1`/`TIER_2`/`TIER_3`) are more self-documenting in a raw `psql` session than the
bare integers `1`/`2`/`3` would be.

**Decision.** `postgres_graph_store.py`'s blast-radius scoring reads `services.tier`
via raw SQL (`text(...)`), which sees the actual stored label — the string
`"TIER_1"`, not the int `1`. `_TIER_WEIGHT` is keyed by those strings
(`{"TIER_1": 1.0, "TIER_2": 0.6, "TIER_3": 0.3}`) specifically because of this, with a
comment pointing back at this ADR so the next raw-SQL query against `services.tier`
doesn't repeat the same wrong assumption. Caught before ever hitting a live database —
by re-reading Phase 1's own ADR on `values_callable` before writing the scoring code,
not by a failing test.

## 3. A bind parameter immediately followed by `::` never gets substituted

**Context.** The CTE's seed clause was originally written as
`WHERE s.id = ANY(:start_ids::uuid[])`. Every `pytest` run against this failed with
`asyncpg.exceptions.PostgresSyntaxError: syntax error at or near ":"` — but the
*compiled* SQL SQLAlchemy logged showed `:workspace_id` and `:max_depth` correctly
turned into `$1`/`$2` while `:start_ids::uuid[]` was left completely untouched, still
literally `:start_ids::uuid[]`, which asyncpg then couldn't parse at all.

**Decision.** SQLAlchemy's textual-SQL bind-parameter scanner treats a colon
immediately followed by another colon as *not* a bind parameter (a deliberate
disambiguation against Postgres's `::` cast operator elsewhere in a query) — so
`:start_ids::uuid[]` was silently never recognized as containing a bind param at all.
The fix is a single space: `:start_ids ::uuid[]`. Whitespace before `::` is
semantically inert in Postgres, so this doesn't change the query, only which regex path
SQLAlchemy's parser takes. Both raw-SQL sites in `postgres_graph_store.py` (`_reach_cte`
and the tier lookup) use the spaced form now. This is exactly the class of bug ruff and
mypy cannot see — both passed the whole time — and was only caught by actually running
the tests against a live Postgres, which is why `test_graph.py` exists as real
integration tests rather than mocked ones.

## 4. Blast-radius scoring sums edge weight along a path — caught by code review, not by the original tests

**Context.** The FRD's documented formula is `score = Σ over edges in path of
edge_weight(criticality) * tier_weight(reached_service.tier) / depth` — since
`tier_weight` and `depth` are constant across a single path, this reduces to
`(Σ edge_weight) * tier_weight / depth`. The first implementation instead computed the
*mean* of the path's edge weights (`sum(...) / len(criticalities)`). The original test
suite (`test_hard_edge_scores_higher_than_soft_edge`) only exercised depth-1 paths,
where a sum of one term and a mean of one term are identical, so the bug was invisible
to it.

**Decision.** Changed to a plain sum, matching the FRD exactly. A new regression test
(`test_score_sums_edge_weights_along_a_mixed_criticality_path`) builds a 2-hop path with
one hard and one soft edge and asserts the exact resulting score (`0.7`, not the `0.35`
the averaging bug would have produced) — a value assertion, not just an ordering
assertion, specifically so a future regression here fails loudly instead of silently
passing a same-order-different-magnitude check. Found by the code-reviewer sub-agent
reading the FRD's Σ notation literally against the code, not by manual testing —
exactly the failure mode the review step exists to catch.

## 5. Blast-radius `path` resolves to full `ServiceOut` objects, not bare UUIDs

**Context.** The FRD documents `BlastRadiusEntry{service: ServiceOut, score: float,
path: list[ServiceOut], depth: int}` so a client can render the explanatory path
without a further round-trip per service. The first implementation typed
`BlastRadiusEntryOut.path` as `list[uuid.UUID]` and returned the raw CTE path array
directly — a mismatch caught in code review.

**Decision.** Added `catalog_service.get_services_by_ids`, a single batch query
(`WHERE workspace_id = :workspace_id AND id = ANY(...)`) that resolves every id
referenced across an entire blast-radius response (both each entry's own service and
every hop in every path) in one round trip, rather than one query per hop. The route
builds one `dict[UUID, Service]` from that batch and looks each id up in memory when
constructing the response — avoids the N+1 that a naive per-id `get_service` call would
have introduced once paths get long.

## 6. Catalog import resolves `team_name` against existing workspace teams too, and rolls back on an unknown one

**Context.** `import_catalog`'s edge-name resolution already checked both the current
payload and the workspace's pre-existing services, rolling back with
`ValidationAppError` on an unresolvable name. The first draft of team-name resolution
for services only checked the current payload's teams — an import that referenced an
already-existing team (created in a prior import, or by hand) silently set
`team_id = None` instead of resolving it or rejecting the import, inconsistent with
every other resolution path in the same function.

**Decision.** `team_by_name` is now seeded from the workspace's existing teams before
merging in the payload's newly-created ones, and an unresolvable `team_name` now raises
`ValidationAppError` (with `db.rollback()`, so nothing partially applies) exactly like
an unresolvable edge endpoint does. Two regression tests cover both directions: importing
a service that references a team created in an earlier, separate request, and importing
one that references a team name that doesn't exist anywhere.

## 7. `create_service`/`update_service` validate `team_id` against the workspace

**Context.** `create_edge` already re-fetches both endpoints scoped to `workspace_id`
before creating an edge, so a cross-workspace `service_id` reads as 404 rather than
silently creating a tenant-straddling edge. `create_service`/`update_service` accepted
`team_id` without the equivalent check — not exploitable today (nothing reads a
service's team across a workspace boundary yet), but a defense-in-depth gap relative to
the rest of the module's discipline, raised as a NOTE in code review and fixed
alongside the BLOCKING findings since the fix was one `get_team` call in each function.

## 8. Line endings are pinned to LF via `.gitattributes`, found while trying to push

**Context.** This branch touches only backend files, but `git push` was blocked by the
pre-push hook's frontend `prettier --check` step failing across all 42 frontend files —
none of which this branch modified. `frontend/.prettierrc` sets `"endOfLine": "lf"`;
this machine's `core.autocrlf=true` converts every file to CRLF on checkout, so the
`web` container's bind-mounted view of every frontend file had CRLF line endings that
prettier flagged as unformatted, independent of any actual content change.

**Decision.** Added a repo-root `.gitattributes` with `* text=auto eol=lf`, which pins
checkout-time line endings to LF regardless of a given machine's local `core.autocrlf`
setting — the correct fix at the repository level rather than asking every contributor
to reconfigure their own git install (which `git config` changes wouldn't even persist
across clones, and CLAUDE.md's git-safety rule forbids touching git config as a
workaround anyway). Adding the file alone wasn't enough — the already-checked-out
working tree still had CRLF on disk, and neither `git add --renormalize .` nor a plain
`git checkout -- .` rewrote it, because git's own modified-file detection (via
`core.autocrlf`'s clean filter) considered the working copy unchanged relative to the
index even though the *actual bytes on disk* didn't match the new `eol=lf` attribute.
Forcing an actual rewrite required deleting the tracked files from disk and checking
them out fresh (`git ls-files -z | xargs -0 rm -f && git checkout -- .`), which have no
prior on-disk copy to compare against and so unconditionally re-materialize under the
current attributes. Not fixed by disabling the hook or skipping it with `--no-verify` —
per CLAUDE.md, a failing hook means fix the underlying cause, not bypass the gate.
