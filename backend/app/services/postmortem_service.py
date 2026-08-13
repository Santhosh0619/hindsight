import uuid

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.pagination import decode_cursor, encode_cursor
from app.models.postmortem import Postmortem, PostmortemChunk, PostmortemStatus
from app.schemas.postmortem import PostmortemCreate
from app.workers import queue

logger = get_logger(__name__)


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
) -> tuple[list[Postmortem], str | None]:
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
    return rows, next_cursor


async def get_postmortem(
    db: AsyncSession, workspace_id: uuid.UUID, postmortem_id: uuid.UUID
) -> Postmortem:
    postmortem = await db.get(Postmortem, postmortem_id)
    if postmortem is None or postmortem.workspace_id != workspace_id:
        raise NotFoundError("Postmortem not found")
    return postmortem


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
