# FRD: Hybrid Retrieval

## API Endpoints (Backend — FastAPI)

### `GET /workspaces/{workspace_id}/search`
- Auth: any workspace member (`get_current_workspace`) — read-only, no role gate.
- Query: `q: str` (min length 1), `mode: Literal["hybrid","vector","keyword","graph"] =
  "hybrid"`, `limit: int = Query(default=settings.retrieval_top_k, ge=1, le=100)`.
- Response `200`: `SearchResponseOut{results: list[SearchResultOut], mode,
  timings_ms: dict[str,int]}`. `SearchResultOut{postmortem: PostmortemOut, score: float,
  sources: list[SourceHitOut], chunk_excerpt: ChunkExcerptOut | None,
  graph_reason: GraphReasonOut | None}`. `SourceHitOut{source: Literal["vector",
  "keyword","graph"], rank: int, raw_score: float}`.
- Errors: `422` (empty query), `404` (non-member, via existing `get_current_workspace`).

All error responses use the existing `{"error": {"code","message","detail"}}` envelope.

## React Components (Frontend)

### `frontend/src/pages/Search.tsx` (F10)
Replaces the `/search` stub route. A text input (debounced), a mode toggle
(hybrid/vector/keyword/graph — a segmented control, not a dropdown, since all four
options should be visible at once per plan.md's framing of F10 as the screen that
makes retrieval mechanics visible), and a result list. Each result card shows the
postmortem title/severity/date, the best-matching chunk excerpt (when the result has
one), a graph-reasoning line (when the result came via graph — "via checkout-api's
neighbor payments-svc"), and one `Badge` chip per entry in `sources` naming which
retriever(s) found it, each ranked (e.g. "vector #2"). Uses React Query's `useQuery`
keyed on `[workspace_id, mode, debounced_query]`; empty query shows `EmptyState`
prompting a search, not an error; a query with zero results shows a distinct
`EmptyState` saying so; loading state uses `LoadingSkeleton`.

### `frontend/src/lib/api.ts` (extended)
`search(workspaceId, { q, mode, limit }) -> Promise<SearchResponseOut>` — a thin
`apiFetch` wrapper, matching every other typed API call in this file.

### `frontend/src/lib/types.ts` (extended)
`SearchMode`, `SourceHitOut`, `ChunkExcerptOut`, `GraphReasonOut`, `SearchResultOut`,
`SearchResponseOut` — hand-kept in sync with `backend/app/schemas/search.py`, matching
this file's existing no-codegen convention.

## Data Model Changes

None — this phase reads `postmortems`, `postmortem_chunks` (`embedding`, `tsv`
columns, both already indexed since Phase 1), `postmortem_services`, and the catalog
(`services`, `service_edges` via `GraphStore`). No new tables or columns.

## Internal Architecture

### `app/services/retrieval/vector.py`

```python
class VectorHit(BaseModel):
    chunk_id: UUID
    postmortem_id: UUID
    distance: float  # cosine distance, lower = closer
    rank: int         # 1-indexed

async def search_vector(
    db: AsyncSession, *, workspace_id: UUID, query_embedding: list[float],
    top_k: int, max_distance: float = 0.7,
) -> list[VectorHit]: ...
```

One query: join `postmortem_chunks` to `postmortems` (for `workspace_id` scoping,
since chunks don't carry `workspace_id` directly), order by
`embedding.cosine_distance(query_embedding)`, filter `distance <= max_distance`, limit
`top_k`. `max_distance=0.7` is a tunable constant (documented, not hardcoded inline)
chosen so a query with nothing meaningfully close returns fewer than `top_k` results
instead of padding with unrelated noise — see the ADR for the empirical basis.

### `app/services/retrieval/keyword.py`

```python
class KeywordHit(BaseModel):
    chunk_id: UUID
    postmortem_id: UUID
    score: float  # BM25 score after rerank, higher = more relevant
    rank: int

async def search_keyword(
    db: AsyncSession, *, workspace_id: UUID, query: str, top_k: int,
) -> list[KeywordHit]: ...
```

Two stages: (1) a Postgres query using `websearch_to_tsquery('english', :query)`
against `postmortem_chunks.tsv`, ranked by `ts_rank_cd`, workspace-scoped, capped at a
candidate-set size (`top_k * 4`, tunable) — `websearch_to_tsquery` specifically because
it never raises a syntax error on arbitrary user input (unlike `to_tsquery`), which
matters for a public-facing search box. (2) `rank_bm25.BM25Okapi` reranks that
candidate set in memory (tokenize each candidate chunk's content plus the query with a
simple lowercase/word-boundary tokenizer), producing the final `top_k` — a second,
independently-computed relevance signal on the same candidates, not just relying on
Postgres's own ranking alone.

### `app/services/retrieval/graph.py`

```python
class GraphHit(BaseModel):
    postmortem_id: UUID
    score: float
    matched_service_id: UUID
    matched_service_name: str
    via_service_id: UUID | None  # None if the postmortem links directly to the matched
                                  # service; set if reached through its neighborhood
    via_service_name: str | None
    role: ServiceLinkRole
    rank: int

async def search_graph(
    db: AsyncSession, graph_store: GraphStore, *, workspace_id: UUID, query: str,
    top_k: int,
) -> list[GraphHit]: ...
```

1. Case-insensitive substring match of the query against the workspace's service
   names (`catalog_service.list_services`) — a service is a candidate if its name
   appears in the query text. No fuzzy matching this phase (out of scope: query
   understanding).
2. For each matched service, `graph_store.neighborhood(workspace_id, [id], k=2)`
   (Phase 4's existing method — this phase adds no new graph traversal logic).
3. Fetch `postmortem_services` rows linking to any matched or neighbor service;
   `score = role_weight(role) * recency_weight(postmortem.occurred_at)`, where
   `role_weight` is `{root_cause: 1.0, affected: 0.6, downstream: 0.3}` (mirrors Phase
   4's blast-radius criticality-weighting pattern) and `recency_weight` decays linearly
   over a 180-day window, floored at 0.2 for anything older (a very old postmortem is
   still relevant context, just weighted down, never zeroed out).

### `app/services/retrieval/fusion.py`

```python
def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[UUID]], *, k: int,
) -> dict[UUID, float]: ...
```

`ranked_lists` maps source name (`"vector"`/`"keyword"`/`"graph"`) to that source's
ranked postmortem-id list (already deduplicated to one entry per postmortem — the best
rank among that postmortem's hits, computed by the caller before fusion, since RRF
operates on ranks, not raw scores, and a postmortem can appear via multiple chunks
within one source). Returns `{postmortem_id: summed_rrf_score}` for every id appearing
in at least one list. Pure function, no I/O — trivially unit-testable against
hand-constructed ranked lists with a known expected output.

### `app/services/retrieval/hybrid.py`

```python
class RetrievalResult(BaseModel):
    results: list[SearchResultOut]
    timings_ms: dict[str, int]

async def hybrid_search(
    db: AsyncSession, graph_store: GraphStore, *, workspace_id: UUID, query: str,
    mode: Literal["hybrid", "vector", "keyword", "graph"], top_k: int,
) -> RetrievalResult: ...
```

For `mode="hybrid"`: runs `search_vector`, `search_keyword`, `search_graph`
concurrently via `asyncio.gather` (each independently timed, contributing to
`timings_ms`), collapses each to a per-postmortem best-rank list, fuses via
`reciprocal_rank_fusion` (`k=settings.rrf_k`), sorts by fused score descending, and
assembles `SearchResultOut` entries — the `sources` list on each result comes directly
from which of the three per-source lists contained that postmortem id, at what rank,
with what raw score (not recomputed or approximated). For a single mode, runs only
that one retriever and skips fusion (the single source's own ranking is the final
order — FR-06). `chunk_excerpt` is populated from the best-matching chunk (vector or
keyword hit) when available; `graph_reason` is populated from the `GraphHit`'s
matched/via-service fields when the result came via graph.

### `app/api/v1/search.py`

Thin FastAPI router; constructs a `PostgresGraphStore(db)` (Phase 4) and calls
`hybrid_search`; maps the result into `SearchResponseOut`.

### `app/schemas/search.py`

The Pydantic v2 request/response models listed under Endpoints.

## Dependencies

Depends on Phase 1's `postmortem_chunks` (`embedding`/`tsv` columns, already indexed),
Phase 4's `GraphStore`/`PostgresGraphStore`/`catalog_service.list_services`, Phase 5's
`embed()`, and Phase 6's `postmortem_services`/`ServiceLinkRole`. Every later module
needing retrieval (Phase 8's retriever node, Phase 12's evaluation harness) depends on
this phase's `hybrid_search` as the single entry point.

## Sequence Flows

**Hybrid search**
1. `GET /search?q=...&mode=hybrid` → `get_current_workspace` resolves membership (404
   if not a member) → `hybrid_search(db, graph_store, workspace_id=..., query=...,
   mode="hybrid", top_k=...)`.
2. `search_vector`/`search_keyword`/`search_graph` run concurrently.
3. Each source's hits collapse to one best-rank entry per postmortem id.
4. `reciprocal_rank_fusion` combines the three per-source ranked lists into one fused
   score per postmortem id appearing in any of them.
5. Results sort by fused score descending; each carries its full per-source
   attribution, not just the final number.

**Single-mode search**
1. `GET /search?q=...&mode=vector` → only `search_vector` runs.
2. Its own ranking is the final order — no fusion step, no other retriever invoked.

## Edge Cases & Error Handling

| Edge case | Handling |
|---|---|
| Empty/whitespace-only query | `422`, rejected by `SearchQuery`'s Pydantic validator before any retrieval runs |
| Query matches nothing in any source | `200` with `results: []`, not an error — a real "nothing found," distinguishable in the UI from a loading/error state |
| Query matches a service name that has no linked postmortems | Graph retrieval contributes zero hits for that query; other modes/sources unaffected |
| A postmortem found by more than one retriever in hybrid mode | Appears once, with multiple entries in `sources`, RRF-scored using all its per-source ranks |
| `mode` is a single retriever | Fusion is skipped entirely; that retriever's own ranking is authoritative |
| Non-member queries another workspace's search | `404`, via the existing `get_current_workspace` dependency |
| A workspace with zero postmortems/services | All three retrievers return empty lists cleanly; no error, no special-casing needed |
