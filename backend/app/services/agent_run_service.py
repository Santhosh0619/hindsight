import uuid

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.models.agent import AgentRun, AgentRunStep
from app.models.incident import Brief, Incident
from app.schemas.agent_run import (
    AgentRunDetailOut,
    AgentRunOut,
    AgentRunStatsOut,
    AgentRunStepOut,
)

DEFAULT_LIST_LIMIT = 20


def _to_out(run: AgentRun, *, incident_title: str, from_cache: bool) -> AgentRunOut:
    return AgentRunOut(
        id=run.id,
        incident_id=run.incident_id,
        incident_title=incident_title,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_tokens_in=run.total_tokens_in,
        total_tokens_out=run.total_tokens_out,
        from_cache=from_cache,
    )


async def list_runs(
    db: AsyncSession, *, workspace_id: uuid.UUID, cursor: str | None, limit: int
) -> tuple[list[AgentRunOut], str | None]:
    query = (
        select(AgentRun, Incident.title, Brief.from_cache)
        .join(Incident, Incident.id == AgentRun.incident_id)
        .outerjoin(Brief, Brief.id == AgentRun.brief_id)
        .where(Incident.workspace_id == workspace_id)
    )
    if cursor is not None:
        cursor_started_at, cursor_id = decode_cursor(cursor)
        query = query.where(
            tuple_(AgentRun.started_at, AgentRun.id) < (cursor_started_at, cursor_id)
        )
    query = query.order_by(AgentRun.started_at.desc(), AgentRun.id.desc()).limit(limit + 1)

    result = await db.execute(query)
    rows = result.all()

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last_run = rows[-1][0]
        next_cursor = encode_cursor(last_run.started_at, last_run.id)

    items = [
        _to_out(run, incident_title=title, from_cache=bool(from_cache))
        for run, title, from_cache in rows
    ]
    return items, next_cursor


async def get_run_detail(
    db: AsyncSession, *, workspace_id: uuid.UUID, run_id: uuid.UUID
) -> AgentRunDetailOut:
    run_result = await db.execute(
        select(AgentRun, Incident.title, Brief.from_cache)
        .join(Incident, Incident.id == AgentRun.incident_id)
        .outerjoin(Brief, Brief.id == AgentRun.brief_id)
        .where(AgentRun.id == run_id, Incident.workspace_id == workspace_id)
    )
    row = run_result.first()
    if row is None:
        raise NotFoundError("Agent run not found")
    run, incident_title, from_cache = row

    steps_result = await db.execute(
        select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.seq)
    )
    steps = [
        AgentRunStepOut(
            id=step.id,
            seq=step.seq,
            node_name=step.node_name,
            status=step.status,
            latency_ms=step.latency_ms,
            tokens_in=step.tokens_in,
            tokens_out=step.tokens_out,
            output_summary=step.output_summary,
            error=step.error,
        )
        for step in steps_result.scalars().all()
    ]

    base = _to_out(run, incident_title=incident_title, from_cache=bool(from_cache))
    return AgentRunDetailOut(**base.model_dump(), steps=steps)


async def get_stats(db: AsyncSession, *, workspace_id: uuid.UUID) -> AgentRunStatsOut:
    totals_result = await db.execute(
        select(
            func.count(AgentRun.id),
            func.coalesce(func.sum(AgentRun.total_tokens_in), 0),
            func.coalesce(func.sum(AgentRun.total_tokens_out), 0),
        )
        .join(Incident, Incident.id == AgentRun.incident_id)
        .where(Incident.workspace_id == workspace_id)
    )
    total_runs, total_tokens_in, total_tokens_out = totals_result.one()

    cache_hit_rate: float | None = None
    if total_runs > 0:
        hits_result = await db.execute(
            select(func.count(AgentRun.id))
            .join(Incident, Incident.id == AgentRun.incident_id)
            .join(Brief, Brief.id == AgentRun.brief_id)
            .where(Incident.workspace_id == workspace_id, Brief.from_cache.is_(True))
        )
        cache_hits = hits_result.scalar_one()
        cache_hit_rate = cache_hits / total_runs

    return AgentRunStatsOut(
        total_runs=total_runs,
        total_tokens_in=total_tokens_in,
        total_tokens_out=total_tokens_out,
        cache_hit_rate=cache_hit_rate,
    )
