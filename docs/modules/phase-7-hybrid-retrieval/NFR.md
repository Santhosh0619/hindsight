# NFR: Hybrid Retrieval

## Performance

- `mode=hybrid` runs all three retrievers concurrently via `asyncio.gather`, not
  sequentially — total latency is bounded by the slowest single retriever, not the
  sum of all three.
- Keyword retrieval's BM25 rerank operates on a bounded candidate set (`top_k * 4`
  from the Postgres `ts_rank_cd` stage), not the whole corpus — reranking cost scales
  with the candidate window, not table size.
- Vector search uses the existing HNSW index (`ix_postmortem_chunks_embedding_hnsw`,
  Phase 1) and a `max_distance` filter, so a query with nothing close returns quickly
  with few/no rows rather than scanning and returning `top_k` worth of weak matches.
- `timings_ms` in the response breaks out each retriever's own latency (and the fusion
  step, in hybrid mode) — not just total request time — so a slow retriever is visible
  in the response itself, not just inferred from an overall number.

## Security

- Every retrieval query is `workspace_id`-scoped at the service-layer function
  boundary (`search_vector`/`search_keyword`/`search_graph` all take `workspace_id` as
  a required parameter and filter by it), matching the discipline established since
  Phase 1 — a member of workspace A can never retrieve workspace B's postmortems
  regardless of `mode`.
- Read access requires only workspace membership — no new RBAC mechanism, matching
  Phase 4's read-vs-write split (retrieval is read-only, no role gate needed).
- The raw query string reaches Postgres only through parameterized queries
  (`websearch_to_tsquery`'s argument is always bound, never string-interpolated) and
  through the local embedding model (no LLM call, no injection surface — this phase
  makes no model API calls at all, unlike Phase 6).

## Reliability

- A workspace with no postmortems, no services, or no graph edges yet returns clean
  empty results from every retriever — no exception, no special-casing required by
  the caller.
- `reciprocal_rank_fusion` is a pure function (no I/O, no exceptions from malformed
  input by construction — it only ever receives already-validated ranked lists from
  its own callers) — the one piece of this phase's logic with zero external failure
  modes to reason about.
- BM25 reranking never raises on an empty candidate set or an empty query token
  list — an empty corpus produces an empty ranked list, not an exception.

## Observability

- `structlog` event per search request (`search_completed`, with `mode`,
  `result_count`, and `timings_ms`) at `info` level, matching every prior phase's
  mutation/completion logging pattern (even though this is a read, not a mutation —
  search volume and latency are worth the same visibility).

## Testability

- Backend: `test_fusion.py` covers `reciprocal_rank_fusion` in isolation against
  hand-constructed ranked lists with known expected scores (no DB, no async — the one
  pure-function test in this phase, fast and exhaustive). `test_retrieval.py` covers
  each of `search_vector`/`search_keyword`/`search_graph` against a fixture corpus
  designed so each retriever's acceptance criterion is independently checkable: a
  vector-only-findable postmortem (no shared vocabulary), a keyword-only-findable one
  (a rare exact error string embeddings represent badly), and a graph-only-findable
  one (linked to a neighbor service, never mentions the queried service by name).
  `test_search_api.py` covers the endpoint: all four modes return visibly different
  result sets on that same fixture, `source_attribution` is accurate (never invented,
  never missing a real contributor), cross-tenant 404, empty-query 422.
- All backend tests run against a real Postgres (HNSW/tsvector/GIN behavior can't be
  meaningfully verified against a mock, same rationale as every prior phase touching
  these indexes).
- Frontend: component tests for the mode toggle and result-chip rendering; e2e
  (Playwright, against the isolated test stack) covers the real acceptance-criteria
  loop — search a fixture workspace, switch modes, see visibly different results and
  correct source chips, in a real browser.

## Constraints

- Everything from Phases 1-6's NFRs still applies (async throughout, Pydantic v2 at
  every boundary, typed exceptions, `mypy --strict` clean, no bare dicts,
  `workspace_id` filtering on every tenant-scoped query, TypeScript strict on the
  frontend, React Query for server state).
- No new database tables/migrations — built entirely on Phase 1's existing
  `postmortem_chunks` (`embedding`/`tsv`) and Phase 6's `postmortem_services` schema.
- No LLM call anywhere in this phase — retrieval is embedding + Postgres + graph
  traversal only, matching plan.md §10's "no key at all" degradation level (search
  must fully function with `llm_api_key` unset, same as ingestion).
- `rank_bm25` reranking happens in the request path (not a background job) — bounded
  candidate-set size (NFR Performance) is what keeps this from becoming a blocking-call
  problem; if the candidate set ever needed to grow past what's safe to rerank
  synchronously, that would be a future phase's problem to revisit, not this one's to
  pre-solve.
