import asyncio
import time
import uuid
from typing import Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models.postmortem import Postmortem, PostmortemChunk
from app.schemas.postmortem import PostmortemOut
from app.schemas.search import (
    ChunkExcerptOut,
    GraphReasonOut,
    SearchMode,
    SearchResponseOut,
    SearchResultOut,
    SourceHitOut,
)
from app.services.graph_store import GraphStore
from app.services.ingestion.embed import embed
from app.services.retrieval.fusion import reciprocal_rank_fusion
from app.services.retrieval.graph import GraphHit, search_graph
from app.services.retrieval.keyword import KeywordHit, search_keyword
from app.services.retrieval.vector import VectorHit, search_vector

logger = get_logger(__name__)


class _HasPostmortemId(Protocol):
    postmortem_id: uuid.UUID
    rank: int


_H = TypeVar("_H", bound=_HasPostmortemId)


def _best_hit_per_postmortem(hits: list[_H]) -> dict[uuid.UUID, _H]:
    # Every hit list here is already sorted best-first (rank ascending) by its own
    # producer, so the first occurrence of a postmortem id is its best hit.
    best: dict[uuid.UUID, _H] = {}
    for hit in hits:
        best.setdefault(hit.postmortem_id, hit)
    return best


def _ranked_ids(best: dict[uuid.UUID, _H]) -> list[uuid.UUID]:
    return [hit.postmortem_id for hit in sorted(best.values(), key=lambda h: h.rank)]


async def hybrid_search(
    db: AsyncSession,
    graph_store: GraphStore,
    *,
    workspace_id: uuid.UUID,
    query: str,
    mode: SearchMode,
    top_k: int,
) -> SearchResponseOut:
    settings = get_settings()
    session_factory = get_session_factory()
    timings_ms: dict[str, int] = {}

    async def _timed_vector() -> list[VectorHit]:
        start = time.monotonic()
        query_embedding = (await embed([query]))[0]
        # A fresh session, not the caller's `db` -- SQLAlchemy's AsyncSession isn't
        # safe for concurrent use from multiple coroutines, and this runs alongside
        # keyword/graph via asyncio.gather in hybrid mode.
        async with session_factory() as session:
            hits = await search_vector(
                session, workspace_id=workspace_id, query_embedding=query_embedding, top_k=top_k
            )
        timings_ms["vector"] = int((time.monotonic() - start) * 1000)
        return hits

    async def _timed_keyword() -> list[KeywordHit]:
        start = time.monotonic()
        async with session_factory() as session:
            hits = await search_keyword(
                session, workspace_id=workspace_id, query=query, top_k=top_k
            )
        timings_ms["keyword"] = int((time.monotonic() - start) * 1000)
        return hits

    async def _timed_graph() -> list[GraphHit]:
        # Uses the caller's `db`/`graph_store` directly -- safe because this is the
        # only concurrent task touching that session (vector/keyword each use their
        # own fresh one above).
        start = time.monotonic()
        hits = await search_graph(
            db, graph_store, workspace_id=workspace_id, query=query, top_k=top_k
        )
        timings_ms["graph"] = int((time.monotonic() - start) * 1000)
        return hits

    vector_hits: list[VectorHit] = []
    keyword_hits: list[KeywordHit] = []
    graph_hits: list[GraphHit] = []

    if mode == "hybrid":
        vector_hits, keyword_hits, graph_hits = await asyncio.gather(
            _timed_vector(), _timed_keyword(), _timed_graph()
        )
    elif mode == "vector":
        vector_hits = await _timed_vector()
    elif mode == "keyword":
        keyword_hits = await _timed_keyword()
    else:
        graph_hits = await _timed_graph()

    vector_best = _best_hit_per_postmortem(vector_hits)
    keyword_best = _best_hit_per_postmortem(keyword_hits)
    graph_best = _best_hit_per_postmortem(graph_hits)

    ranked_lists: dict[str, list[uuid.UUID]] = {}
    if vector_best:
        ranked_lists["vector"] = _ranked_ids(vector_best)
    if keyword_best:
        ranked_lists["keyword"] = _ranked_ids(keyword_best)
    if graph_best:
        ranked_lists["graph"] = _ranked_ids(graph_best)

    fusion_start = time.monotonic()
    fused_scores = reciprocal_rank_fusion(ranked_lists, k=settings.rrf_k)
    ordered_ids = sorted(fused_scores, key=lambda pid: fused_scores[pid], reverse=True)[:top_k]
    if mode == "hybrid":
        timings_ms["fusion"] = int((time.monotonic() - fusion_start) * 1000)

    if not ordered_ids:
        logger.info("search_completed", mode=mode, result_count=0, timings_ms=timings_ms)
        return SearchResponseOut(results=[], mode=mode, timings_ms=timings_ms)

    postmortems_result = await db.execute(
        select(Postmortem).where(
            Postmortem.workspace_id == workspace_id, Postmortem.id.in_(ordered_ids)
        )
    )
    postmortem_by_id = {p.id: p for p in postmortems_result.scalars().all()}

    excerpt_chunk_ids = {
        (vector_best[pid] if pid in vector_best else keyword_best[pid]).chunk_id
        for pid in ordered_ids
        if pid in vector_best or pid in keyword_best
    }
    chunk_by_id: dict[uuid.UUID, PostmortemChunk] = {}
    if excerpt_chunk_ids:
        chunks_result = await db.execute(
            select(PostmortemChunk).where(PostmortemChunk.id.in_(excerpt_chunk_ids))
        )
        chunk_by_id = {c.id: c for c in chunks_result.scalars().all()}

    def _sources(pid: uuid.UUID) -> list[SourceHitOut]:
        sources: list[SourceHitOut] = []
        if pid in vector_best:
            vector_hit = vector_best[pid]
            sources.append(
                SourceHitOut(source="vector", rank=vector_hit.rank, raw_score=vector_hit.distance)
            )
        if pid in keyword_best:
            keyword_hit = keyword_best[pid]
            sources.append(
                SourceHitOut(source="keyword", rank=keyword_hit.rank, raw_score=keyword_hit.score)
            )
        if pid in graph_best:
            graph_hit = graph_best[pid]
            sources.append(
                SourceHitOut(source="graph", rank=graph_hit.rank, raw_score=graph_hit.score)
            )
        return sources

    results: list[SearchResultOut] = []
    for pid in ordered_ids:
        postmortem = postmortem_by_id.get(pid)
        if postmortem is None:
            continue

        excerpt_chunk_id = None
        if pid in vector_best:
            excerpt_chunk_id = vector_best[pid].chunk_id
        elif pid in keyword_best:
            excerpt_chunk_id = keyword_best[pid].chunk_id
        chunk_excerpt = None
        if excerpt_chunk_id is not None:
            chunk = chunk_by_id.get(excerpt_chunk_id)
            if chunk is not None:
                chunk_excerpt = ChunkExcerptOut(
                    chunk_id=chunk.id, section_label=chunk.section_label, content=chunk.content
                )

        graph_reason = None
        if pid in graph_best:
            g = graph_best[pid]
            graph_reason = GraphReasonOut(
                matched_service_name=g.matched_service_name,
                via_service_name=g.via_service_name,
                role=g.role,
            )

        results.append(
            SearchResultOut(
                postmortem=PostmortemOut.model_validate(postmortem),
                score=fused_scores[pid],
                sources=_sources(pid),
                chunk_excerpt=chunk_excerpt,
                graph_reason=graph_reason,
            )
        )

    logger.info("search_completed", mode=mode, result_count=len(results), timings_ms=timings_ms)
    return SearchResponseOut(results=results, mode=mode, timings_ms=timings_ms)
