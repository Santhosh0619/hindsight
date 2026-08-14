import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Brief, Incident, IncidentSignal, IncidentStatus
from app.models.postmortem import Postmortem, PostmortemStatus
from app.schemas.catalog import ServiceOut
from app.schemas.dashboard import (
    DashboardOut,
    FragileServiceOut,
    IngestHealthOut,
    MttrPointOut,
    RecentBriefOut,
)
from app.services import catalog_service
from app.services.graph_store import GraphStore

MTTR_TREND_WEEKS = 8
RECENT_BRIEFS_LIMIT = 10
FRAGILE_SERVICES_LIMIT = 10


def _week_start(dt: datetime) -> date:
    d = dt.date()
    return d - timedelta(days=d.weekday())


async def _open_incidents(db: AsyncSession, *, workspace_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(Incident.id)).where(
            Incident.workspace_id == workspace_id, Incident.status == IncidentStatus.OPEN
        )
    )
    return result.scalar_one()


async def _ingest_health(db: AsyncSession, *, workspace_id: uuid.UUID) -> IngestHealthOut:
    result = await db.execute(
        select(Postmortem.status, func.count())
        .where(Postmortem.workspace_id == workspace_id)
        .group_by(Postmortem.status)
    )
    counts: dict[PostmortemStatus, int] = {status: count for status, count in result.all()}
    return IngestHealthOut(
        indexed=counts.get(PostmortemStatus.INDEXED, 0),
        processing=counts.get(PostmortemStatus.PROCESSING, 0),
        pending=counts.get(PostmortemStatus.PENDING, 0),
        failed=counts.get(PostmortemStatus.FAILED, 0),
    )


async def _briefs_generated(db: AsyncSession, *, workspace_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(Brief.id))
        .join(Incident, Incident.id == Brief.incident_id)
        .where(Incident.workspace_id == workspace_id)
    )
    return result.scalar_one()


async def _mttr_trend(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[MttrPointOut]:
    now = datetime.now(UTC)
    current_week_start = _week_start(now)
    earliest_week_start = current_week_start - timedelta(weeks=MTTR_TREND_WEEKS - 1)
    earliest_cutoff = datetime(
        earliest_week_start.year, earliest_week_start.month, earliest_week_start.day, tzinfo=UTC
    )

    result = await db.execute(
        select(Incident.opened_at, Incident.resolved_at).where(
            Incident.workspace_id == workspace_id,
            Incident.resolved_at.is_not(None),
            Incident.resolved_at >= earliest_cutoff,
        )
    )

    buckets: dict[date, list[float]] = {
        current_week_start - timedelta(weeks=i): [] for i in range(MTTR_TREND_WEEKS)
    }
    for opened_at, resolved_at in result.all():
        week = _week_start(resolved_at)
        bucket = buckets.get(week)
        if bucket is not None:
            bucket.append((resolved_at - opened_at).total_seconds() / 60)

    return [
        MttrPointOut(week_start=week, mttr_minutes=(sum(values) / len(values)) if values else None)
        for week, values in sorted(buckets.items())
    ]


async def _fragile_services(
    db: AsyncSession, graph_store: GraphStore, *, workspace_id: uuid.UUID
) -> list[FragileServiceOut]:
    services = await catalog_service.list_services(db, workspace_id)
    if not services:
        return []

    unnested = (
        select(
            IncidentSignal.incident_id,
            func.unnest(IncidentSignal.affected_service_ids).label("service_id"),
        )
        .join(Incident, Incident.id == IncidentSignal.incident_id)
        .where(Incident.workspace_id == workspace_id)
        .subquery()
    )
    count_result = await db.execute(
        select(unnested.c.service_id, func.count(func.distinct(unnested.c.incident_id))).group_by(
            unnested.c.service_id
        )
    )
    incident_count_by_service: dict[uuid.UUID, int] = {
        service_id: count for service_id, count in count_result.all()
    }

    entries = []
    for service in services:
        # Sequential, not gathered concurrently -- graph_store shares this call's
        # single AsyncSession, and running concurrent queries on one session is the
        # exact failure ADR 0007 §1 and ADR 0008 §4 both already hit and fixed; not
        # worth reintroducing for a loop bounded by catalog size (<=40 in Phase 11).
        radius = await graph_store.blast_radius(workspace_id, [service.id])
        incident_count = incident_count_by_service.get(service.id, 0)
        blast_radius_size = len(radius.entries)
        entries.append(
            FragileServiceOut(
                service=ServiceOut.model_validate(service),
                incident_count=incident_count,
                blast_radius_size=blast_radius_size,
                fragility_score=incident_count * (1 + blast_radius_size),
            )
        )
    entries.sort(key=lambda e: (-e.fragility_score, e.service.name))
    return entries[:FRAGILE_SERVICES_LIMIT]


async def _recent_briefs(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[RecentBriefOut]:
    result = await db.execute(
        select(Brief, Incident.title)
        .join(Incident, Incident.id == Brief.incident_id)
        .where(Incident.workspace_id == workspace_id)
        .order_by(Brief.generated_at.desc().nulls_last())
        .limit(RECENT_BRIEFS_LIMIT)
    )
    return [
        RecentBriefOut(
            incident_id=brief.incident_id,
            incident_title=title,
            brief_id=brief.id,
            version=brief.version,
            overall_confidence=brief.overall_confidence,
            generated_at=brief.generated_at,
        )
        for brief, title in result.all()
    ]


async def get_dashboard(
    db: AsyncSession, graph_store: GraphStore, *, workspace_id: uuid.UUID
) -> DashboardOut:
    open_incidents = await _open_incidents(db, workspace_id=workspace_id)
    ingest_health = await _ingest_health(db, workspace_id=workspace_id)
    briefs_generated = await _briefs_generated(db, workspace_id=workspace_id)
    mttr_trend = await _mttr_trend(db, workspace_id=workspace_id)
    recent_briefs = await _recent_briefs(db, workspace_id=workspace_id)
    fragile_services = await _fragile_services(db, graph_store, workspace_id=workspace_id)

    corpus_size = (
        ingest_health.indexed
        + ingest_health.processing
        + ingest_health.pending
        + ingest_health.failed
    )

    return DashboardOut(
        open_incidents=open_incidents,
        briefs_generated=briefs_generated,
        corpus_size=corpus_size,
        ingest_health=ingest_health,
        mttr_trend=mttr_trend,
        fragile_services=fragile_services,
        recent_briefs=recent_briefs,
    )
