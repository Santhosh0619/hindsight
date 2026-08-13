import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.postmortem import (
    FactType,
    FailureMode,
    Postmortem,
    PostmortemFact,
    PostmortemFailureMode,
    PostmortemService,
)
from app.schemas.postmortem import PostmortemChunkOut
from app.services import catalog_service, postmortem_service
from app.services.extraction.facts_agent import extract_facts
from app.services.extraction.failure_mode_agent import classify_failure_modes
from app.services.extraction.service_linker_agent import link_services
from app.services.llm.router import LLMRouter

logger = get_logger(__name__)


class ExtractionSummary(BaseModel):
    fact_count: int
    failure_mode_count: int
    service_link_count: int


_EMPTY_SUMMARY = ExtractionSummary(fact_count=0, failure_mode_count=0, service_link_count=0)

_FACT_LIST_TYPES = (
    (FactType.TRIGGER, "triggers"),
    (FactType.ROOT_CAUSE, "root_causes"),
    (FactType.REMEDIATION, "remediations"),
    (FactType.DETECTION_GAP, "detection_gaps"),
    (FactType.CONTRIBUTING_FACTOR, "contributing_factors"),
)


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


async def run_extraction(
    db: AsyncSession, router: LLMRouter, *, postmortem_id: uuid.UUID
) -> ExtractionSummary:
    postmortem = await db.get(Postmortem, postmortem_id)
    if postmortem is None:
        # Deleted before the job ran -- nothing to extract, not a failure.
        return _EMPTY_SUMMARY

    workspace_id = postmortem.workspace_id
    chunk_rows = await postmortem_service.list_chunks(db, postmortem_id)
    chunks = [PostmortemChunkOut.model_validate(row) for row in chunk_rows]
    known_chunk_ids = {chunk.id for chunk in chunks}

    services = await catalog_service.list_services(db, workspace_id)
    service_id_by_name = {service.name: service.id for service in services}

    facts_result = await extract_facts(router, chunks=chunks)
    failure_mode_result = await classify_failure_modes(router, chunks=chunks)
    service_link_result = await link_services(
        router, chunks=chunks, known_service_names=list(service_id_by_name)
    )

    fact_count = 0
    for fact_type, field_name in _FACT_LIST_TYPES:
        for item in getattr(facts_result, field_name):
            # Hallucination guard: a fact citing a chunk_id we didn't actually give
            # the model is dropped, never persisted -- deterministic, not left to the
            # model's discretion.
            if item.chunk_id not in known_chunk_ids:
                continue
            db.add(
                PostmortemFact(
                    postmortem_id=postmortem_id,
                    fact_type=fact_type,
                    statement=item.statement,
                    confidence=item.confidence,
                    source_chunk_id=item.chunk_id,
                )
            )
            fact_count += 1

    failure_mode_count = 0
    for classification in failure_mode_result.classifications:
        failure_mode = await _get_or_create_failure_mode(
            db, workspace_id=workspace_id, label=classification.family.value
        )
        db.add(
            PostmortemFailureMode(
                postmortem_id=postmortem_id,
                failure_mode_id=failure_mode.id,
                confidence=classification.confidence,
            )
        )
        failure_mode_count += 1

    service_link_count = 0
    for link in service_link_result.links:
        # Drop names the model returns that aren't in the real catalog -- never
        # invent a service.
        service_id = service_id_by_name.get(link.service_name)
        if service_id is None:
            continue
        db.add(
            PostmortemService(
                postmortem_id=postmortem_id,
                service_id=service_id,
                role=link.role,
                confidence=link.confidence,
            )
        )
        service_link_count += 1

    await db.commit()
    return ExtractionSummary(
        fact_count=fact_count,
        failure_mode_count=failure_mode_count,
        service_link_count=service_link_count,
    )
