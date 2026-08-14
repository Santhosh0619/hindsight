import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.build_graph import build_graph, checkpointer_conn_string
from app.agents.state import initial_state
from app.agents.streaming import stream_graph_events
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.pagination import decode_cursor, encode_cursor
from app.models.agent import AgentRun
from app.models.incident import Brief, BriefFeedback, Incident, IncidentSignal, IncidentStatus
from app.models.postmortem import Postmortem, PostmortemChunk
from app.schemas.catalog import BlastRadiusEntryOut, BlastRadiusOut, ServiceOut
from app.schemas.incident import CandidateMatch, Citation, Hypothesis, RunbookStepDraft
from app.schemas.incident_api import (
    BriefFeedbackCreate,
    BriefFeedbackOut,
    BriefOut,
    CitationOut,
    HypothesisOut,
    IncidentCreate,
    IncidentUpdate,
    MatchedPostmortemOut,
    RunbookStepOut,
)
from app.schemas.postmortem import PostmortemOut
from app.services import catalog_service
from app.services.graph_store import BlastRadius, GraphStore
from app.services.llm.router import LLMRouter

logger = get_logger(__name__)


async def create_incident(
    db: AsyncSession, *, workspace_id: uuid.UUID, opened_by: uuid.UUID, payload: IncidentCreate
) -> Incident:
    incident = Incident(
        workspace_id=workspace_id,
        external_ref=payload.external_ref,
        title=payload.title,
        raw_alert_text=payload.raw_alert_text,
        severity=payload.severity.value if payload.severity else None,
        status=IncidentStatus.OPEN,
        opened_by=opened_by,
        opened_at=datetime.now(UTC),
    )
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    logger.info("incident_created", incident_id=str(incident.id), workspace_id=str(workspace_id))
    return incident


async def list_incidents(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    status: IncidentStatus | None,
    severity: str | None,
    service_id: uuid.UUID | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[Incident], str | None]:
    query = select(Incident).where(Incident.workspace_id == workspace_id)
    if status is not None:
        query = query.where(Incident.status == status)
    if severity is not None:
        query = query.where(Incident.severity == severity)
    if service_id is not None:
        # Matches any historical signal, not only the most recent one -- see FRD.
        query = query.where(
            Incident.id.in_(
                select(IncidentSignal.incident_id).where(
                    IncidentSignal.affected_service_ids.contains([service_id])
                )
            )
        )
    if cursor is not None:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.where(
            tuple_(Incident.created_at, Incident.id) < (cursor_created_at, cursor_id)
        )
    query = query.order_by(Incident.created_at.desc(), Incident.id.desc()).limit(limit + 1)
    result = await db.execute(query)
    rows = list(result.scalars().all())

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return rows, next_cursor


async def get_incident(
    db: AsyncSession, workspace_id: uuid.UUID, incident_id: uuid.UUID
) -> Incident:
    incident = await db.get(Incident, incident_id)
    if incident is None or incident.workspace_id != workspace_id:
        raise NotFoundError("Incident not found")
    return incident


async def update_incident(
    db: AsyncSession, *, incident: Incident, payload: IncidentUpdate
) -> Incident:
    if payload.title is not None:
        incident.title = payload.title
    if payload.status is not None:
        incident.status = payload.status
        resolved_statuses = (IncidentStatus.RESOLVED, IncidentStatus.FALSE_POSITIVE)
        if payload.status in resolved_statuses and incident.resolved_at is None:
            incident.resolved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(incident)
    return incident


async def get_brief(db: AsyncSession, *, incident_id: uuid.UUID, brief_id: uuid.UUID) -> Brief:
    brief = await db.get(Brief, brief_id)
    if brief is None or brief.incident_id != incident_id:
        raise NotFoundError("Brief not found")
    return brief


async def list_briefs(
    db: AsyncSession, *, incident_id: uuid.UUID, workspace_id: uuid.UUID
) -> list[BriefOut]:
    result = await db.execute(
        select(Brief).where(Brief.incident_id == incident_id).order_by(Brief.version.desc())
    )
    return [
        await _enrich_brief(db, row, workspace_id=workspace_id) for row in result.scalars().all()
    ]


async def record_feedback(
    db: AsyncSession, *, brief_id: uuid.UUID, user_id: uuid.UUID, payload: BriefFeedbackCreate
) -> BriefFeedbackOut:
    feedback = BriefFeedback(
        brief_id=brief_id,
        user_id=user_id,
        verdict=payload.verdict,
        correct_postmortem_id=payload.correct_postmortem_id,
        note=payload.note,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return BriefFeedbackOut.model_validate(feedback)


async def _start_agent_run(db: AsyncSession, *, incident_id: uuid.UUID) -> AgentRun:
    run = AgentRun(
        incident_id=incident_id,
        graph_version="1",
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def _finish_agent_run(db: AsyncSession, *, run: AgentRun, status: str) -> None:
    run.status = status
    run.finished_at = datetime.now(UTC)
    await db.commit()


async def generate_brief(
    db: AsyncSession, graph_store: GraphStore, router: LLMRouter, *, incident: Incident
) -> BriefOut:
    settings = get_settings()
    run = await _start_agent_run(db, incident_id=incident.id)
    logger.info("brief_generation_started", incident_id=str(incident.id))
    start = time.monotonic()

    status = "done"
    try:
        conn_string = checkpointer_conn_string(settings)
        # Table/index setup runs once at app startup (main.py's lifespan), not here --
        # see that comment for why running it per-request against a session that's
        # mid-transaction for the whole graph run is a real deadlock, not just waste.
        async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
            graph = build_graph(db, graph_store, router, checkpointer=saver)
            state = initial_state(
                incident_id=incident.id,
                workspace_id=incident.workspace_id,
                raw_text=incident.raw_alert_text,
            )
            final_state = await graph.ainvoke(
                state, config={"configurable": {"thread_id": str(incident.id)}}
            )
    except Exception:
        status = "error"
        raise
    finally:
        await _finish_agent_run(db, run=run, status=status)

    brief = final_state["final"]
    logger.info(
        "brief_generation_completed",
        incident_id=str(incident.id),
        llm_used=brief.llm_used,
        correction_passes=brief.correction_passes,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
    brief_row = await db.get(Brief, brief.id)
    assert brief_row is not None
    return await _enrich_brief(db, brief_row, workspace_id=incident.workspace_id)


async def stream_brief_generation(
    db: AsyncSession, graph_store: GraphStore, router: LLMRouter, *, incident: Incident
) -> AsyncIterator[dict[str, object]]:
    settings = get_settings()
    run = await _start_agent_run(db, incident_id=incident.id)
    logger.info("brief_generation_started", incident_id=str(incident.id))

    status = "done"
    try:
        conn_string = checkpointer_conn_string(settings)
        # Table/index setup runs once at app startup -- see generate_brief's comment.
        async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
            graph = build_graph(db, graph_store, router, checkpointer=saver)
            state = initial_state(
                incident_id=incident.id,
                workspace_id=incident.workspace_id,
                raw_text=incident.raw_alert_text,
            )
            async for event in stream_graph_events(
                graph, state, thread_id=str(incident.id), run_id=run.id
            ):
                if event.get("type") == "error":
                    status = "error"
                yield event
    except Exception:
        status = "error"
        raise
    finally:
        await _finish_agent_run(db, run=run, status=status)
        logger.info("brief_generation_completed", incident_id=str(incident.id), status=status)


async def _enrich_blast_radius(
    db: AsyncSession, blast_radius: BlastRadius, *, workspace_id: uuid.UUID
) -> BlastRadiusOut:
    # Mirrors app/api/v1/catalog.py's get_blast_radius route exactly -- Phase 8's
    # graph_store.BlastRadius only carries service ids; the API response needs the
    # resolved name/tier a human (or F6's blast radius panel) actually reads.
    referenced_ids = {entry.service_id for entry in blast_radius.entries}
    for entry in blast_radius.entries:
        referenced_ids.update(entry.path.service_ids)
    services_by_id = await catalog_service.get_services_by_ids(
        db, workspace_id, list(referenced_ids)
    )

    entries = [
        BlastRadiusEntryOut(
            service=ServiceOut.model_validate(services_by_id[entry.service_id]),
            score=entry.score,
            path=[ServiceOut.model_validate(services_by_id[sid]) for sid in entry.path.service_ids],
            depth=entry.depth,
        )
        for entry in blast_radius.entries
        if entry.service_id in services_by_id
        and all(sid in services_by_id for sid in entry.path.service_ids)
    ]
    return BlastRadiusOut(services=entries)


async def _enrich_brief(db: AsyncSession, brief_row: Brief, *, workspace_id: uuid.UUID) -> BriefOut:
    hypotheses = [Hypothesis.model_validate(h) for h in brief_row.hypotheses]
    matched = [CandidateMatch.model_validate(c) for c in brief_row.matched_postmortems]
    runbook_steps = [RunbookStepDraft.model_validate(s) for s in brief_row.runbook_steps]
    citations = [Citation.model_validate(c) for c in brief_row.citations]
    blast_radius = BlastRadius.model_validate(brief_row.blast_radius)
    blast_radius_out = await _enrich_blast_radius(db, blast_radius, workspace_id=workspace_id)

    chunk_ids: set[uuid.UUID] = {c.chunk_id for c in citations}
    for hypothesis in hypotheses:
        chunk_ids.update(c.chunk_id for c in hypothesis.citations)
    for step in runbook_steps:
        if step.citation is not None:
            chunk_ids.add(step.citation.chunk_id)

    postmortem_ids: set[uuid.UUID] = {c.postmortem_id for c in citations}
    postmortem_ids.update(m.postmortem_id for m in matched)

    chunk_by_id: dict[uuid.UUID, PostmortemChunk] = {}
    if chunk_ids:
        chunk_result = await db.execute(
            select(PostmortemChunk).where(PostmortemChunk.id.in_(chunk_ids))
        )
        chunk_by_id = {c.id: c for c in chunk_result.scalars().all()}

    postmortem_by_id: dict[uuid.UUID, Postmortem] = {}
    if postmortem_ids:
        postmortem_result = await db.execute(
            select(Postmortem).where(Postmortem.id.in_(postmortem_ids))
        )
        postmortem_by_id = {p.id: p for p in postmortem_result.scalars().all()}

    def _citation_out(citation: Citation) -> CitationOut | None:
        chunk = chunk_by_id.get(citation.chunk_id)
        postmortem = postmortem_by_id.get(citation.postmortem_id)
        if chunk is None or postmortem is None:
            return None
        return CitationOut(
            chunk_id=citation.chunk_id,
            postmortem_id=citation.postmortem_id,
            postmortem_title=postmortem.title,
            quote=citation.quote,
            content=chunk.content,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
        )

    hypotheses_out: list[HypothesisOut] = []
    for hypothesis in hypotheses:
        resolved = [c for c in (_citation_out(c) for c in hypothesis.citations) if c is not None]
        if resolved:
            hypotheses_out.append(
                HypothesisOut(
                    statement=hypothesis.statement,
                    confidence=hypothesis.confidence,
                    citations=resolved,
                )
            )

    runbook_steps_out = [
        RunbookStepOut(
            step=step.step,
            source_postmortem_id=step.source_postmortem_id,
            citation=_citation_out(step.citation) if step.citation is not None else None,
        )
        for step in runbook_steps
    ]

    citations_out = [c for c in (_citation_out(c) for c in citations) if c is not None]

    matched_out: list[MatchedPostmortemOut] = []
    for candidate in matched:
        postmortem = postmortem_by_id.get(candidate.postmortem_id)
        if postmortem is None:
            continue
        matched_out.append(
            MatchedPostmortemOut(
                postmortem=PostmortemOut.model_validate(postmortem),
                vector_score=candidate.vector_score,
                keyword_score=candidate.keyword_score,
                graph_score=candidate.graph_score,
                failure_mode_overlap=candidate.failure_mode_overlap,
                recency=candidate.recency,
                overall_score=candidate.overall_score,
                rank=candidate.rank,
            )
        )

    return BriefOut(
        id=brief_row.id,
        incident_id=brief_row.incident_id,
        version=brief_row.version,
        hypotheses=hypotheses_out,
        matched_postmortems=matched_out,
        blast_radius=blast_radius_out,
        runbook_steps=runbook_steps_out,
        citations=citations_out,
        overall_confidence=brief_row.overall_confidence,
        correction_passes=brief_row.correction_passes,
        llm_used=brief_row.llm_used,
        from_cache=brief_row.from_cache,
        generated_at=brief_row.generated_at,
    )
