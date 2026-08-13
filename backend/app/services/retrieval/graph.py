import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Service
from app.models.postmortem import Postmortem, PostmortemService, ServiceLinkRole
from app.services import catalog_service
from app.services.graph_store import GraphStore

# Mirrors Phase 4's blast-radius criticality weighting: a service a postmortem names as
# its root cause matters more to a graph-driven match than one it merely mentions.
_ROLE_WEIGHT = {
    ServiceLinkRole.ROOT_CAUSE: 1.0,
    ServiceLinkRole.AFFECTED: 0.6,
    ServiceLinkRole.DOWNSTREAM: 0.3,
}
_RECENCY_WINDOW_DAYS = 180
_MIN_RECENCY_WEIGHT = 0.2


class GraphHit(BaseModel):
    postmortem_id: uuid.UUID
    score: float
    matched_service_id: uuid.UUID
    matched_service_name: str
    via_service_id: uuid.UUID | None
    via_service_name: str | None
    role: ServiceLinkRole
    rank: int


def _recency_weight(occurred_at: datetime | None) -> float:
    # A very old postmortem is still relevant context -- weighted down, never zeroed.
    if occurred_at is None:
        return _MIN_RECENCY_WEIGHT
    age_days = (datetime.now(UTC) - occurred_at).days
    if age_days <= 0:
        return 1.0
    if age_days >= _RECENCY_WINDOW_DAYS:
        return _MIN_RECENCY_WEIGHT
    fraction = age_days / _RECENCY_WINDOW_DAYS
    return 1.0 - fraction * (1.0 - _MIN_RECENCY_WEIGHT)


async def search_graph(
    db: AsyncSession,
    graph_store: GraphStore,
    *,
    workspace_id: uuid.UUID,
    query: str,
    top_k: int,
) -> list[GraphHit]:
    services = await catalog_service.list_services(db, workspace_id)
    lowered_query = query.lower()
    matched_services = [s for s in services if s.name.lower() in lowered_query]
    if not matched_services:
        return []

    service_by_id = {s.id: s for s in services}

    # candidate service_id -> (the matched service that reached it, via_service or None)
    candidates: dict[uuid.UUID, tuple[Service, Service | None]] = {}
    for matched in matched_services:
        candidates.setdefault(matched.id, (matched, None))
        # Expanded one matched service at a time (not batched) so each neighbor keeps
        # a clear "via" attribution for the UI's graph_reason explanation.
        neighbor_ids = await graph_store.neighborhood(workspace_id, [matched.id], k=2)
        for neighbor_id in neighbor_ids:
            if neighbor_id in candidates:
                continue
            neighbor = service_by_id.get(neighbor_id)
            if neighbor is not None:
                candidates[neighbor_id] = (matched, neighbor)

    links_result = await db.execute(
        select(PostmortemService, Postmortem)
        .join(Postmortem, Postmortem.id == PostmortemService.postmortem_id)
        .where(PostmortemService.service_id.in_(candidates.keys()))
    )

    best_by_postmortem: dict[uuid.UUID, GraphHit] = {}
    for link, postmortem in links_result:
        matched, via = candidates[link.service_id]
        score = _ROLE_WEIGHT.get(link.role, 0.0) * _recency_weight(postmortem.occurred_at)
        existing = best_by_postmortem.get(link.postmortem_id)
        if existing is not None and existing.score >= score:
            continue
        best_by_postmortem[link.postmortem_id] = GraphHit(
            postmortem_id=link.postmortem_id,
            score=score,
            matched_service_id=matched.id,
            matched_service_name=matched.name,
            via_service_id=via.id if via else None,
            via_service_name=via.name if via else None,
            role=link.role,
            rank=0,
        )

    ranked = sorted(best_by_postmortem.values(), key=lambda hit: hit.score, reverse=True)[:top_k]
    return [hit.model_copy(update={"rank": i + 1}) for i, hit in enumerate(ranked)]
