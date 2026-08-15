"""`make seed` entrypoint — the only script in this package that touches the
database. Loads the fixtures `generate_*.py` already produced (never regenerates
them) into the demo workspace: catalog, postmortems (through the real ingestion
pipeline, with ground-truth facts/service-links/failure-modes inserted directly --
FRD Gap #2/#3), incidents, precomputed briefs for 8 of them (via the real
retriever/correlator nodes against the real indexed corpus -- FRD Gap #4), and eval
cases. Idempotent (FR-06): each section is skipped if the workspace already has rows
for it, so running `make seed` again after a partial failure or a redeploy is safe.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import correlator_node, retriever_node
from app.agents.state import initial_state
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, get_session_factory
from app.models.catalog import Service
from app.models.evaluation import EvalCase
from app.models.incident import Brief, BriefStatus, Incident
from app.models.incident import IncidentSignal as IncidentSignalRow
from app.models.postmortem import (
    FactType,
    FailureMode,
    Postmortem,
    PostmortemChunk,
    PostmortemFact,
    PostmortemFailureMode,
    PostmortemService,
    PostmortemStatus,
    ServiceLinkRole,
    Severity,
)
from app.models.workspace import Workspace
from app.schemas.catalog import CatalogImport
from app.schemas.incident import Citation, Hypothesis, NormalizedSignal, RunbookStepDraft
from app.services import catalog_service
from app.services.ingestion.chunk import chunk
from app.services.ingestion.embed import embed
from app.services.ingestion.redact import redact
from app.services.ingestion.screen import screen
from app.services.postgres_graph_store import PostgresGraphStore
from app.services.workspace_service import slugify_unique

logger = get_logger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


async def _get_or_create_demo_workspace(db: AsyncSession) -> Workspace:
    # Same lookup create_demo_guest (Phase 2) already uses -- whichever of the two
    # runs first creates the row the other then finds (FRD Gap #7).
    result = await db.execute(select(Workspace).where(Workspace.is_demo.is_(True)).limit(1))
    workspace = result.scalar_one_or_none()
    if workspace is not None:
        return workspace

    workspace = Workspace(
        name="Demo Workspace",
        slug=await slugify_unique(db, "demo-workspace"),
        is_demo=True,
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def _seed_catalog(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    existing = await db.execute(
        select(func.count(Service.id)).where(Service.workspace_id == workspace_id)
    )
    if existing.scalar_one() > 0:
        logger.info("catalog_already_seeded", workspace_id=str(workspace_id))
        return

    fixture = json.loads((FIXTURES_DIR / "catalog.json").read_text())
    payload = CatalogImport.model_validate(fixture["import"])
    result = await catalog_service.import_catalog(db, workspace_id=workspace_id, payload=payload)
    logger.info(
        "catalog_seeded",
        teams=result.teams_created,
        services=result.services_created,
        edges=result.edges_created,
    )


async def _ingest_one(
    db: AsyncSession, *, workspace_id: uuid.UUID, entry: dict[str, Any]
) -> Postmortem:
    postmortem = Postmortem(
        workspace_id=workspace_id,
        title=str(entry["title"]),
        raw_text=str(entry["raw_text"]),
        occurred_at=datetime.fromisoformat(str(entry["occurred_at"]).removesuffix("Z")).replace(
            tzinfo=UTC
        ),
        duration_minutes=int(entry["duration_minutes"]),
        severity=Severity(entry["severity"]),
        status=PostmortemStatus.PENDING,
    )
    db.add(postmortem)
    await db.flush()

    postmortem.status = PostmortemStatus.PROCESSING
    redacted = redact(postmortem.raw_text)
    injection_flagged = screen(redacted)
    spans = chunk(redacted)
    embeddings = await embed([span.content for span in spans])

    postmortem.redacted_text = redacted
    postmortem.injection_flagged = injection_flagged
    for chunk_index, (span, embedding) in enumerate(zip(spans, embeddings, strict=True)):
        db.add(
            PostmortemChunk(
                postmortem_id=postmortem.id,
                chunk_index=chunk_index,
                section_label=span.section_label,
                content=span.content,
                char_start=span.char_start,
                char_end=span.char_end,
                embedding=embedding,
                tsv=func.to_tsvector("english", span.content),
            )
        )
    postmortem.status = PostmortemStatus.INDEXED
    await db.flush()
    return postmortem


async def _get_or_create_failure_mode(
    db: AsyncSession, *, workspace_id: uuid.UUID, label: str
) -> FailureMode:
    result = await db.execute(
        select(FailureMode).where(
            FailureMode.workspace_id == workspace_id, FailureMode.label == label
        )
    )
    existing = result.scalars().first()
    if existing is not None:
        return existing
    failure_mode = FailureMode(workspace_id=workspace_id, label=label)
    db.add(failure_mode)
    await db.flush()
    return failure_mode


async def _seed_postmortems(
    db: AsyncSession, workspace_id: uuid.UUID
) -> dict[str, list[uuid.UUID]]:
    """Returns scenario_key -> [postmortem_id, ...] so incidents/eval cases can
    resolve ground truth without knowing ids ahead of time (FRD Gap #4)."""
    fixture: list[dict[str, Any]] = json.loads((FIXTURES_DIR / "postmortems.json").read_text())

    existing = await db.execute(
        select(Postmortem.title, Postmortem.id).where(Postmortem.workspace_id == workspace_id)
    )
    postmortem_id_by_title = {title: pm_id for title, pm_id in existing.all()}

    services_result = await db.execute(select(Service).where(Service.workspace_id == workspace_id))
    service_by_name = {s.name: s for s in services_result.scalars().all()}

    ids_by_scenario: dict[str, list[uuid.UUID]] = {}
    created = 0
    for entry in fixture:
        scenario_key = str(entry["scenario_key"])
        title = str(entry["title"])

        if title in postmortem_id_by_title:
            ids_by_scenario.setdefault(scenario_key, []).append(postmortem_id_by_title[title])
            continue

        postmortem = await _ingest_one(db, workspace_id=workspace_id, entry=entry)
        created += 1

        chunks_result = await db.execute(
            select(PostmortemChunk).where(PostmortemChunk.postmortem_id == postmortem.id)
        )
        chunk_by_section = {c.section_label: c for c in chunks_result.scalars().all()}

        facts = entry["facts"]
        assert isinstance(facts, list)
        for fact in facts:
            section_chunk = chunk_by_section.get(fact["section_label"])
            if section_chunk is None:
                continue
            db.add(
                PostmortemFact(
                    postmortem_id=postmortem.id,
                    fact_type=FactType(fact["fact_type"]),
                    statement=str(fact["statement"]),
                    confidence=0.9,
                    source_chunk_id=section_chunk.id,
                )
            )

        affected_names = entry["affected_service_names"]
        assert isinstance(affected_names, list)
        for name in affected_names:
            service = service_by_name.get(str(name))
            if service is None:
                continue
            db.add(
                PostmortemService(
                    postmortem_id=postmortem.id,
                    service_id=service.id,
                    role=ServiceLinkRole.ROOT_CAUSE,
                    confidence=0.9,
                )
            )

        failure_mode = await _get_or_create_failure_mode(
            db, workspace_id=workspace_id, label=str(entry["failure_mode"])
        )
        db.add(
            PostmortemFailureMode(
                postmortem_id=postmortem.id, failure_mode_id=failure_mode.id, confidence=0.9
            )
        )
        await db.commit()

        ids_by_scenario.setdefault(scenario_key, []).append(postmortem.id)

    logger.info("postmortems_seeded", created=created, already_present=len(fixture) - created)
    return ids_by_scenario


async def _resolve_affected_service_ids(
    db: AsyncSession, scenario_postmortem_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    services_result = await db.execute(
        select(PostmortemService.service_id)
        .where(PostmortemService.postmortem_id.in_(scenario_postmortem_ids))
        .distinct()
    )
    return [row[0] for row in services_result.all()]


async def _precompute_brief(
    db: AsyncSession,
    graph_store: PostgresGraphStore,
    *,
    incident: Incident,
    affected_service_ids: list[uuid.UUID],
) -> None:
    state = initial_state(
        incident_id=incident.id,
        workspace_id=incident.workspace_id,
        raw_text=incident.raw_alert_text,
    )
    state["signal"] = NormalizedSignal(
        symptoms=[incident.raw_alert_text],
        error_strings=[],
        metrics={},
        affected_service_ids=affected_service_ids,
        unresolved_mentions=[],
        time_window=None,
        severity_guess=Severity(incident.severity) if incident.severity else None,
        extracted_by_model=None,
        extraction_confidence=None,
    )
    state["llm_used"] = False

    retrieval_update = await retriever_node(state, db=db, graph_store=graph_store)
    state.update(retrieval_update)  # type: ignore[typeddict-item]
    correlator_update = await correlator_node(state, db=db, graph_store=graph_store)
    state.update(correlator_update)  # type: ignore[typeddict-item]

    candidates = state["candidates"]
    blast_radius = state["blast_radius"]
    assert blast_radius is not None

    top_match = candidates[0] if candidates else None
    hypotheses: list[Hypothesis] = []
    runbook_steps: list[RunbookStepDraft] = []
    citations: list[Citation] = []

    if top_match is not None:
        facts_result = await db.execute(
            select(PostmortemFact, PostmortemChunk)
            .join(PostmortemChunk, PostmortemChunk.id == PostmortemFact.source_chunk_id)
            .where(PostmortemFact.postmortem_id == top_match.postmortem_id)
        )
        fact_rows = facts_result.all()

        root_cause_fact = next(
            (f for f, c in fact_rows if f.fact_type == FactType.ROOT_CAUSE), None
        )
        remediation_fact = next(
            (f for f, c in fact_rows if f.fact_type == FactType.REMEDIATION), None
        )

        if root_cause_fact is not None:
            chunk_row = next(c for f, c in fact_rows if f is root_cause_fact)
            citation = Citation(
                chunk_id=chunk_row.id, postmortem_id=top_match.postmortem_id, quote=None
            )
            citations.append(citation)
            hypotheses.append(
                Hypothesis(
                    statement=root_cause_fact.statement,
                    confidence=round(min(0.95, 0.6 + top_match.overall_score * 0.4), 2),
                    citations=[citation],
                )
            )
        if remediation_fact is not None:
            chunk_row = next(c for f, c in fact_rows if f is remediation_fact)
            citation = Citation(
                chunk_id=chunk_row.id, postmortem_id=top_match.postmortem_id, quote=None
            )
            citations.append(citation)
            runbook_steps.append(
                RunbookStepDraft(
                    step=remediation_fact.statement,
                    source_postmortem_id=top_match.postmortem_id,
                    citation=citation,
                )
            )

    overall_confidence = (
        sum(h.confidence for h in hypotheses) / len(hypotheses) if hypotheses else None
    )

    brief_row = Brief(
        incident_id=incident.id,
        version=1,
        status=BriefStatus.READY,
        hypotheses=[h.model_dump(mode="json") for h in hypotheses],
        matched_postmortems=[c.model_dump(mode="json") for c in candidates],
        blast_radius=blast_radius.model_dump(mode="json"),
        runbook_steps=[s.model_dump(mode="json") for s in runbook_steps],
        page_list=[],
        citations=[c.model_dump(mode="json") for c in citations],
        overall_confidence=overall_confidence,
        correction_passes=0,
        llm_used=False,
        from_cache=True,
        generated_at=datetime.now(UTC),
    )
    db.add(brief_row)


async def _seed_incidents(
    db: AsyncSession,
    graph_store: PostgresGraphStore,
    workspace_id: uuid.UUID,
    postmortem_ids_by_scenario: dict[str, list[uuid.UUID]],
) -> None:
    fixture: list[dict[str, Any]] = json.loads((FIXTURES_DIR / "incidents.json").read_text())

    existing = await db.execute(select(Incident.title).where(Incident.workspace_id == workspace_id))
    existing_titles = {title for (title,) in existing.all()}

    created = 0
    briefs_created = 0
    for entry in fixture:
        title = str(entry["title"])
        if title in existing_titles:
            continue

        incident = Incident(
            workspace_id=workspace_id,
            title=title,
            raw_alert_text=str(entry["raw_alert_text"]),
            severity=str(entry["severity"]),
            opened_at=datetime.now(UTC),
        )
        db.add(incident)
        await db.flush()
        created += 1

        scenario_key = str(entry["matched_scenario_key"])
        postmortem_ids = postmortem_ids_by_scenario.get(scenario_key, [])
        affected_service_ids = await _resolve_affected_service_ids(db, postmortem_ids)

        # Every seeded incident gets a real IncidentSignal row, not just the ones with
        # a precomputed brief -- Phase 9's service_id incident filter and Phase 10's
        # dashboard fragility ranking both query this table directly, and would
        # silently treat every seeded incident as affecting no service at all
        # otherwise. normalizer_node writes this same row shape for a live run; this
        # mirrors it exactly, just without an LLM call to produce the symptoms text.
        db.add(
            IncidentSignalRow(
                incident_id=incident.id,
                symptoms={"items": [incident.raw_alert_text], "unresolved_mentions": []},
                error_strings=[],
                metrics={},
                affected_service_ids=affected_service_ids,
                time_window={},
                extracted_by_model=None,
                extraction_confidence=None,
            )
        )

        if entry["has_precomputed_brief"]:
            await _precompute_brief(
                db, graph_store, incident=incident, affected_service_ids=affected_service_ids
            )
            briefs_created += 1

        # One commit per entry -- incident, its signal row, and (if applicable) its
        # precomputed brief land atomically, so a crash mid-entry never leaves a
        # title a rerun would recognize as already-done but is actually incomplete.
        await db.commit()

    logger.info(
        "incidents_seeded",
        created=created,
        already_present=len(fixture) - created,
        briefs_precomputed=briefs_created,
    )


async def _seed_eval_cases(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    postmortem_ids_by_scenario: dict[str, list[uuid.UUID]],
) -> None:
    fixture: list[dict[str, Any]] = json.loads((FIXTURES_DIR / "eval_cases.json").read_text())

    existing = await db.execute(select(EvalCase.name).where(EvalCase.workspace_id == workspace_id))
    existing_names = {name for (name,) in existing.all()}

    created = 0
    for entry in fixture:
        name = str(entry["name"])
        if name in existing_names:
            continue
        db.add(
            EvalCase(
                workspace_id=workspace_id,
                name=name,
                incident_text=str(entry["incident_text"]),
                expected_postmortem_ids=postmortem_ids_by_scenario.get(
                    str(entry["expected_scenario_key"]), []
                ),
                expected_service_ids=[],
            )
        )
        created += 1
    await db.commit()
    logger.info("eval_cases_seeded", created=created, already_present=len(fixture) - created)


async def run() -> None:
    configure_logging()
    start = datetime.now(UTC)
    session_factory = get_session_factory()
    async with session_factory() as db:
        workspace = await _get_or_create_demo_workspace(db)
        await _seed_catalog(db, workspace.id)
        postmortem_ids_by_scenario = await _seed_postmortems(db, workspace.id)
        graph_store = PostgresGraphStore(db)
        await _seed_incidents(db, graph_store, workspace.id, postmortem_ids_by_scenario)
        await _seed_eval_cases(db, workspace.id, postmortem_ids_by_scenario)

    duration = (datetime.now(UTC) - start).total_seconds()
    logger.info(
        "seed_completed", workspace_id=str(workspace.id), duration_seconds=round(duration, 1)
    )
    await dispose_engine()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
