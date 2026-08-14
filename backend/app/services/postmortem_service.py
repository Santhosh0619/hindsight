import uuid

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.pagination import decode_cursor, encode_cursor
from app.models.catalog import Service
from app.models.postmortem import (
    Postmortem,
    PostmortemChunk,
    PostmortemFact,
    PostmortemService,
    PostmortemStatus,
)
from app.schemas.catalog import ServiceOut
from app.schemas.postmortem import (
    PostmortemChunkOut,
    PostmortemCreate,
    PostmortemDetailOut,
    PostmortemFactOut,
    PostmortemOut,
    PostmortemServiceLinkOut,
)
from app.workers import queue

logger = get_logger(__name__)


def _to_postmortem_out(
    row: Postmortem, affected_services: list[PostmortemServiceLinkOut]
) -> PostmortemOut:
    return PostmortemOut(
        id=row.id,
        external_ref=row.external_ref,
        title=row.title,
        occurred_at=row.occurred_at,
        duration_minutes=row.duration_minutes,
        severity=row.severity,
        status=row.status,
        injection_flagged=row.injection_flagged,
        failure_reason=row.failure_reason,
        created_at=row.created_at,
        affected_services=affected_services,
    )


async def _affected_services_by_postmortem_id(
    db: AsyncSession, *, workspace_id: uuid.UUID, postmortem_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PostmortemServiceLinkOut]]:
    """One batched query for every postmortem on a page -- never N+1, matching
    incidents_service._enrich_brief's resolution discipline from Phase 9."""
    if not postmortem_ids:
        return {}
    result = await db.execute(
        select(PostmortemService, Service)
        .join(Service, Service.id == PostmortemService.service_id)
        .where(
            PostmortemService.postmortem_id.in_(postmortem_ids),
            Service.workspace_id == workspace_id,
        )
    )
    by_postmortem: dict[uuid.UUID, list[PostmortemServiceLinkOut]] = {}
    for link, service in result.all():
        by_postmortem.setdefault(link.postmortem_id, []).append(
            PostmortemServiceLinkOut(
                service=ServiceOut.model_validate(service),
                role=link.role,
                confidence=link.confidence,
            )
        )
    return by_postmortem


async def create_postmortem(
    db: AsyncSession, *, workspace_id: uuid.UUID, created_by: uuid.UUID, payload: PostmortemCreate
) -> Postmortem:
    postmortem = Postmortem(
        workspace_id=workspace_id,
        external_ref=payload.external_ref,
        title=payload.title,
        occurred_at=payload.occurred_at,
        duration_minutes=payload.duration_minutes,
        severity=payload.severity,
        raw_text=payload.raw_text,
        status=PostmortemStatus.PENDING,
        created_by=created_by,
    )
    db.add(postmortem)
    await db.commit()
    await db.refresh(postmortem)

    await queue.enqueue(
        db,
        workspace_id=workspace_id,
        kind="ingest_postmortem",
        payload={"postmortem_id": str(postmortem.id)},
    )
    logger.info(
        "postmortem_created", postmortem_id=str(postmortem.id), workspace_id=str(workspace_id)
    )
    return postmortem


async def create_postmortems_bulk(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID,
    items: list[PostmortemCreate],
) -> list[Postmortem]:
    return [
        await create_postmortem(db, workspace_id=workspace_id, created_by=created_by, payload=item)
        for item in items
    ]


async def list_postmortems(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    status: PostmortemStatus | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[PostmortemOut], str | None]:
    query = select(Postmortem).where(Postmortem.workspace_id == workspace_id)
    if status is not None:
        query = query.where(Postmortem.status == status)
    if cursor is not None:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.where(
            tuple_(Postmortem.created_at, Postmortem.id) < (cursor_created_at, cursor_id)
        )
    query = query.order_by(Postmortem.created_at.desc(), Postmortem.id.desc()).limit(limit + 1)
    result = await db.execute(query)
    rows = list(result.scalars().all())

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    affected_by_id = await _affected_services_by_postmortem_id(
        db, workspace_id=workspace_id, postmortem_ids=[r.id for r in rows]
    )
    items = [_to_postmortem_out(r, affected_by_id.get(r.id, [])) for r in rows]
    return items, next_cursor


async def get_postmortem(
    db: AsyncSession, workspace_id: uuid.UUID, postmortem_id: uuid.UUID
) -> Postmortem:
    postmortem = await db.get(Postmortem, postmortem_id)
    if postmortem is None or postmortem.workspace_id != workspace_id:
        raise NotFoundError("Postmortem not found")
    return postmortem


async def get_postmortem_detail(
    db: AsyncSession, workspace_id: uuid.UUID, postmortem_id: uuid.UUID
) -> PostmortemDetailOut:
    postmortem = await get_postmortem(db, workspace_id, postmortem_id)
    chunks = await list_chunks(db, postmortem_id)

    # source_chunk_id is a real, enforced FK (ON DELETE CASCADE) -- a fact can never
    # outlive its chunk, so joining straight to the chunk for its offsets needs no
    # "what if it's missing" branch the way Phase 9's JSONB-stored citations do.
    facts_result = await db.execute(
        select(PostmortemFact, PostmortemChunk)
        .join(PostmortemChunk, PostmortemChunk.id == PostmortemFact.source_chunk_id)
        .where(PostmortemFact.postmortem_id == postmortem_id)
    )
    facts = [
        PostmortemFactOut(
            fact_type=fact.fact_type,
            statement=fact.statement,
            confidence=fact.confidence,
            source_chunk_id=fact.source_chunk_id,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
        )
        for fact, chunk in facts_result.all()
    ]

    affected_by_id = await _affected_services_by_postmortem_id(
        db, workspace_id=workspace_id, postmortem_ids=[postmortem_id]
    )
    base = _to_postmortem_out(postmortem, affected_by_id.get(postmortem_id, []))

    return PostmortemDetailOut(
        id=base.id,
        external_ref=base.external_ref,
        title=base.title,
        occurred_at=base.occurred_at,
        duration_minutes=base.duration_minutes,
        severity=base.severity,
        status=base.status,
        injection_flagged=base.injection_flagged,
        failure_reason=base.failure_reason,
        created_at=base.created_at,
        affected_services=base.affected_services,
        chunks=[PostmortemChunkOut.model_validate(c) for c in chunks],
        redacted_text=postmortem.redacted_text,
        facts=facts,
    )


async def list_chunks(db: AsyncSession, postmortem_id: uuid.UUID) -> list[PostmortemChunk]:
    result = await db.execute(
        select(PostmortemChunk)
        .where(PostmortemChunk.postmortem_id == postmortem_id)
        .order_by(PostmortemChunk.chunk_index)
    )
    return list(result.scalars().all())


async def delete_postmortem(db: AsyncSession, *, postmortem: Postmortem) -> None:
    await db.delete(postmortem)
    await db.commit()
