# ADR 0007: Hybrid Retrieval — Concurrency Safety, Calibration, and Test Design

## 1. Running three retrievers concurrently without breaking `AsyncSession`

**Context.** FR-05 requires `mode=hybrid` to run vector, keyword, and graph retrieval
concurrently via `asyncio.gather`, not sequentially. SQLAlchemy's `AsyncSession` is not
safe for concurrent use by multiple coroutines — two coroutines issuing queries on the
same session at the same time corrupt its internal state, not just race on results.

**Decision.** `hybrid_search` (`app/services/retrieval/hybrid.py`) gives the vector and
keyword tasks each their own fresh session via `get_session_factory()`, since both run
concurrently with the third task and neither owns the caller's session. The graph task
reuses the caller's own `db`/`graph_store` directly — safe specifically because it's the
only one of the three concurrent tasks touching that session. This isn't a general
"always open a fresh session for concurrency" rule; it's "exactly the tasks that share a
session with something else running at the same time need their own." A second
independent code-reviewer pass re-verified this reasoning against the actual
`asyncio.gather` call site before approval, not just the comment claiming it's true.

## 2. `DEFAULT_MAX_DISTANCE=0.7` came from measuring real embeddings, not a guess

**Context.** FR-02 requires vector search to cap results by a maximum cosine-distance
threshold so an unrelated query returns fewer results, not top-k worth of noise. A
threshold picked without measurement is either too tight (misses real paraphrases) or
too loose (returns everything).

**Decision.** Calibrated against this project's actual `sentence-transformers` model by
embedding real paraphrase pairs ("connection pool exhausted" vs. "ran out of DB
connections," ~0.43 distance) and real unrelated pairs (~0.85–1.0 distance) through a
throwaway script before picking `0.7` — comfortably separating the two clusters. This
calibration also caught a wrong initial assumption while writing
`test_keyword_search_finds_an_exact_error_code`: a chunk containing the literal query
string as a substring sits *close* in embedding space (~0.576, well inside the
threshold), not far, because literal-substring chunks are naturally more similar to the
query than two independently-written sentences on the same topic. The test's original
name and assertion (`..._vector_search_misses`) asserted the opposite and was wrong —
caught only by actually running it against the real embeddings, not by reasoning about
it. Renamed to assert only keyword's own positive capability instead of an unprovable
comparative claim.

## 3. Single-mode search still runs through Reciprocal Rank Fusion

**Context.** FR-06 says `mode=vector`/`keyword`/`graph` skip fusion entirely since "a
single ranked list needs no combining."

**Decision.** The code still calls `reciprocal_rank_fusion` with a one-key
`ranked_lists` dict even in single-mode, rather than branching around it. Fusing one
list with itself is mathematically identical to that list's own rank order (monotonic
transform, same relative ordering) — so the observable result is unaffected, but the
result-assembly code downstream (score lookup, `ordered_ids` sort) doesn't need a
separate code path for "was this fused or not." Flagged as a non-blocking FRD-wording
mismatch by code review and left as-is: the FRD's plain-English claim ("skip fusion")
and the code's actual behavior ("fusion is a no-op on one list") describe the same
observable outcome, and the simpler code has one fewer branch to keep correct.

## 4. A regression test that didn't test what its name claimed

**Context.** The first defense-in-depth fix this phase added an explicit
`Postmortem.workspace_id == workspace_id` filter to `search_graph`'s final query
(previously relied on `candidates` being transitively workspace-scoped via
`catalog_service.list_services` upstream — correct today, but a second line of defense
against a future regression in that upstream scoping). The regression test written
alongside it, `test_graph_and_hybrid_mode_never_leak_across_workspaces_with_same_
service_name`, gave two workspaces a same-named service and asserted no leakage — but
same-named services across workspaces always get structurally distinct UUIDs, so
`candidates.keys()` for workspace B could never contain workspace A's service id
regardless of whether the new filter line existed. The test would pass identically with
the fix reverted.

**Decision.** Rewrote it as `test_search_graph_never_returns_a_postmortem_from_
another_workspace`: directly insert a `PostmortemService` row linking workspace A's
postmortem to workspace B's real service id — a data-integrity state the public API can
never produce (service creation and linking always stay within one workspace), engineered
on purpose so `service_b_id` is a genuine candidate in workspace B's own `search_graph`
call. With the filter reverted, this version of the test fails; with it present, it
passes — the first version of any regression test worth keeping should fail against the
bug it claims to guard, and this one didn't until rewritten. Caught by a second
code-reviewer re-review pass looking specifically at whether the test exercised the line
it was named after, not by the first pass.

## 5. E2E needs a real worker, and the first embed() call in a fresh process is slow

**Context.** `docker-compose.test.yml` had no `worker-test` service — every prior
phase's e2e coverage (auth, RBAC) never needed a postmortem actually ingested. Search
does: a postmortem has to reach `status=indexed` (chunked, embedded, written to
`postmortem_chunks`) before it's findable at all.

**Decision.** Added `worker-test`, mirroring the dev `worker` service, sharing the same
`model-cache` named volume as `api-test` and the dev stack (both compose files resolve
to the same default Compose project name from the shared directory, so the volume is
genuinely shared, not just similarly named — avoids redownloading the embedding model
weights per e2e run). Discovered mid-run: the *first* `search.spec.ts` test failed on a
`toBeVisible()` timeout that had nothing to do with search correctness — `api-test` is a
freshly built container, and its first-ever `embed()` call cold-loads
`sentence-transformers`/`torch` into the process, taking longer than a UI assertion's
default 5s timeout. Every subsequent query in the same run was fast, because the model
stayed loaded in that process. Fixed with a `test.beforeAll` hook that fires one
throwaway vector-mode search request before any timed UI assertion runs, so every real
assertion times the feature itself, not the one-time interpreter/model cold start.
Graph mode's fixture (a postmortem linked to a service) needs the extraction agent,
which needs a real LLM — not configured in this e2e stack — so graph-mode-specific e2e
coverage is deferred until Santhosh adds a key; it's already covered at the DB-fixture
level by backend pytest in the meantime.
