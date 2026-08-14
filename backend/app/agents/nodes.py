import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analyst_agent import draft_brief, render_prompt
from app.agents.citation_check import validate_citations
from app.agents.correlator import score_candidates
from app.agents.critic_agent import judge_verification
from app.agents.normalizer_agent import extract_signal
from app.agents.state import TraceEntry, TriageState
from app.core.config import get_settings
from app.core.errors import LLMUnavailableError
from app.models.incident import Brief, BriefStatus
from app.models.incident import IncidentSignal as IncidentSignalRow
from app.models.postmortem import FailureMode, PostmortemFailureMode
from app.schemas.incident import (
    DraftBrief,
    IncidentBrief,
    IncidentSignalOut,
    NormalizedSignal,
    VerificationResult,
)
from app.services import catalog_service
from app.services.graph_store import GraphStore
from app.services.llm import cache as semantic_cache
from app.services.llm.router import LLMRouter
from app.services.retrieval.hybrid import hybrid_search

_CACHE_PURPOSE = "analyst_brief"


def _build_query(signal: NormalizedSignal | None, raw_text: str) -> str:
    if signal is not None and (signal.symptoms or signal.error_strings):
        return " ".join([*signal.symptoms, *signal.error_strings])
    return raw_text


async def _load_failure_mode_labels(
    db: AsyncSession, postmortem_ids: list[uuid.UUID]
) -> dict[uuid.UUID, set[str]]:
    if not postmortem_ids:
        return {}
    result = await db.execute(
        select(PostmortemFailureMode.postmortem_id, FailureMode.label)
        .join(FailureMode, FailureMode.id == PostmortemFailureMode.failure_mode_id)
        .where(PostmortemFailureMode.postmortem_id.in_(postmortem_ids))
    )
    labels_by_postmortem: dict[uuid.UUID, set[str]] = {}
    for postmortem_id, label in result:
        labels_by_postmortem.setdefault(postmortem_id, set()).add(label)
    return labels_by_postmortem


async def normalizer_node(
    state: TriageState, *, db: AsyncSession, router: LLMRouter
) -> dict[str, object]:
    workspace_id = state["workspace_id"]
    services = await catalog_service.list_services(db, workspace_id)
    service_id_by_name = {service.name: service.id for service in services}

    llm_used = True
    try:
        raw_signal = await extract_signal(router, raw_text=state["raw_text"])
    except LLMUnavailableError:
        llm_used = False
        raw_signal = IncidentSignalOut(
            symptoms=[],
            error_strings=[],
            metrics={},
            candidate_service_names=[],
            time_window=None,
            severity_guess=None,
            extraction_confidence=None,
        )

    affected_service_ids: list[uuid.UUID] = []
    unresolved_mentions: list[str] = []
    for name in raw_signal.candidate_service_names:
        service_id = service_id_by_name.get(name)
        if service_id is not None:
            affected_service_ids.append(service_id)
        else:
            unresolved_mentions.append(name)

    signal = NormalizedSignal(
        symptoms=raw_signal.symptoms,
        error_strings=raw_signal.error_strings,
        metrics=raw_signal.metrics,
        affected_service_ids=affected_service_ids,
        unresolved_mentions=unresolved_mentions,
        time_window=raw_signal.time_window,
        severity_guess=raw_signal.severity_guess,
        extracted_by_model=None,
        extraction_confidence=raw_signal.extraction_confidence,
    )

    db.add(
        IncidentSignalRow(
            incident_id=state["incident_id"],
            symptoms={
                "items": raw_signal.symptoms,
                "severity_guess": raw_signal.severity_guess.value
                if raw_signal.severity_guess
                else None,
                "unresolved_mentions": unresolved_mentions,
            },
            error_strings=raw_signal.error_strings,
            metrics=raw_signal.metrics,
            affected_service_ids=affected_service_ids,
            time_window=raw_signal.time_window.model_dump(mode="json")
            if raw_signal.time_window
            else {},
            extracted_by_model=None,
            extraction_confidence=raw_signal.extraction_confidence,
        )
    )
    await db.commit()

    trace = TraceEntry(
        node="normalizer",
        note=(
            f"resolved {len(affected_service_ids)}/{len(raw_signal.candidate_service_names)} "
            f"candidate services"
            if llm_used
            else "no LLM available -- empty signal"
        ),
    )
    return {"signal": signal, "llm_used": llm_used, "trace": [*state["trace"], trace]}


async def retriever_node(
    state: TriageState, *, db: AsyncSession, graph_store: GraphStore
) -> dict[str, object]:
    signal = state["signal"]
    verification = state["verification"]
    is_retry = verification is not None

    base_query = _build_query(signal, state["raw_text"])
    if is_retry:
        assert verification is not None
        query = " ".join([base_query, *verification.suggested_refinements])
        excluded_ids = {c.postmortem_id for c in verification.invalid_citations}
    else:
        query = base_query
        excluded_ids = set()

    settings = get_settings()
    response = await hybrid_search(
        db,
        graph_store,
        workspace_id=state["workspace_id"],
        query=query,
        mode="hybrid",
        top_k=settings.retrieval_top_k,
    )
    if excluded_ids:
        response = response.model_copy(
            update={"results": [r for r in response.results if r.postmortem.id not in excluded_ids]}
        )

    trace = TraceEntry(node="retriever", note=f"{len(response.results)} hits for {query!r}")
    new_retry_count = state["retry_count"] + 1 if is_retry else state["retry_count"]
    return {
        "retrieval": response,
        "retry_count": new_retry_count,
        "trace": [*state["trace"], trace],
    }


async def correlator_node(
    state: TriageState, *, db: AsyncSession, graph_store: GraphStore
) -> dict[str, object]:
    signal = state["signal"]
    retrieval = state["retrieval"]
    assert signal is not None
    assert retrieval is not None

    blast_radius = await graph_store.blast_radius(
        state["workspace_id"], signal.affected_service_ids
    )

    postmortem_ids = [r.postmortem.id for r in retrieval.results]
    labels_by_postmortem = await _load_failure_mode_labels(db, postmortem_ids)
    candidates = score_candidates(retrieval, failure_mode_labels_by_postmortem=labels_by_postmortem)

    trace = TraceEntry(node="correlator", note=f"{len(candidates)} candidates scored")
    return {
        "blast_radius": blast_radius,
        "candidates": candidates,
        "trace": [*state["trace"], trace],
    }


async def analyst_node(
    state: TriageState, *, db: AsyncSession, router: LLMRouter
) -> dict[str, object]:
    signal = state["signal"]
    retrieval = state["retrieval"]
    candidates = state["candidates"]
    assert signal is not None
    assert retrieval is not None

    prompt = render_prompt(signal=signal, candidates=candidates, retrieval=retrieval)

    workspace_id = state["workspace_id"]
    cached = await semantic_cache.get_cached(
        db, workspace_id=workspace_id, purpose=_CACHE_PURPOSE, prompt=prompt
    )
    if cached is not None:
        draft = DraftBrief.model_validate(cached)
        trace = TraceEntry(node="analyst", note="served from semantic cache")
        return {"draft": draft, "from_cache": True, "trace": [*state["trace"], trace]}

    if not state["llm_used"]:
        draft = DraftBrief(hypotheses=[], runbook_steps=[], citations=[])
        trace = TraceEntry(node="analyst", note="no LLM available -- empty draft")
        return {"draft": draft, "trace": [*state["trace"], trace]}

    try:
        draft = await draft_brief(router, prompt=prompt)
    except LLMUnavailableError:
        draft = DraftBrief(hypotheses=[], runbook_steps=[], citations=[])
        trace = TraceEntry(node="analyst", note="LLM became unavailable -- empty draft")
        return {"draft": draft, "llm_used": False, "trace": [*state["trace"], trace]}

    await semantic_cache.store(
        db,
        workspace_id=workspace_id,
        purpose=_CACHE_PURPOSE,
        prompt=prompt,
        # LLMRouter doesn't report which provider in its fallback chain actually
        # served a given call (same gap Phase 6 left for `extracted_by_model`) --
        # the configured primary model is a reasonable label, not a precise claim.
        model=get_settings().llm_model,
        response=draft.model_dump(mode="json"),
    )

    trace = TraceEntry(node="analyst", note=f"{len(draft.hypotheses)} hypotheses drafted")
    return {"draft": draft, "trace": [*state["trace"], trace]}


async def critic_node(state: TriageState, *, router: LLMRouter) -> dict[str, object]:
    draft = state["draft"]
    retrieval = state["retrieval"]
    signal = state["signal"]
    assert draft is not None
    assert retrieval is not None
    assert signal is not None

    cleaned_draft, invalid_citations = validate_citations(draft, retrieval)

    if not state["llm_used"]:
        verification = VerificationResult(
            score=1.0,
            is_grounded=True,
            issues=["no LLM available -- brief is deterministic-only"],
            suggested_refinements=[],
            invalid_citations=invalid_citations,
        )
        trace = TraceEntry(node="critic", note="no LLM available -- pass-through verification")
        return {
            "draft": cleaned_draft,
            "verification": verification,
            "trace": [*state["trace"], trace],
        }

    try:
        judgment = await judge_verification(router, signal=signal, draft=cleaned_draft)
    except LLMUnavailableError:
        verification = VerificationResult(
            score=1.0,
            is_grounded=True,
            issues=["LLM became unavailable -- brief is deterministic-only"],
            suggested_refinements=[],
            invalid_citations=invalid_citations,
        )
        trace = TraceEntry(
            node="critic", note="LLM became unavailable -- pass-through verification"
        )
        return {
            "draft": cleaned_draft,
            "verification": verification,
            "llm_used": False,
            "trace": [*state["trace"], trace],
        }

    verification = VerificationResult(
        score=judgment.score,
        is_grounded=judgment.is_grounded,
        issues=judgment.issues,
        suggested_refinements=judgment.suggested_refinements,
        invalid_citations=invalid_citations,
    )
    trace = TraceEntry(
        node="critic",
        note=(
            f"score={verification.score:.2f}, {len(invalid_citations)} invalid citation(s) dropped"
        ),
    )
    return {
        "draft": cleaned_draft,
        "verification": verification,
        "trace": [*state["trace"], trace],
    }


async def briefer_node(state: TriageState, *, db: AsyncSession) -> dict[str, object]:
    draft = state["draft"]
    verification = state["verification"]
    candidates = state["candidates"]
    blast_radius = state["blast_radius"]
    assert draft is not None
    assert verification is not None
    assert blast_radius is not None

    overall_confidence = (
        sum(h.confidence for h in draft.hypotheses) / len(draft.hypotheses)
        if draft.hypotheses
        else None
    )

    existing_versions = await db.execute(
        select(Brief.version).where(Brief.incident_id == state["incident_id"])
    )
    next_version = max([v for (v,) in existing_versions], default=0) + 1

    brief_row = Brief(
        incident_id=state["incident_id"],
        version=next_version,
        status=BriefStatus.READY,
        hypotheses=[h.model_dump(mode="json") for h in draft.hypotheses],
        matched_postmortems=[c.model_dump(mode="json") for c in candidates],
        blast_radius=blast_radius.model_dump(mode="json"),
        runbook_steps=[s.model_dump(mode="json") for s in draft.runbook_steps],
        page_list=[],
        citations=[c.model_dump(mode="json") for c in draft.citations],
        overall_confidence=overall_confidence,
        correction_passes=state["retry_count"],
        llm_used=state["llm_used"],
        from_cache=state["from_cache"],
        generated_at=datetime.now(UTC),
    )
    db.add(brief_row)
    await db.commit()

    brief = IncidentBrief(
        id=brief_row.id,
        incident_id=state["incident_id"],
        version=next_version,
        hypotheses=draft.hypotheses,
        matched_postmortems=candidates,
        blast_radius=blast_radius,
        runbook_steps=draft.runbook_steps,
        citations=draft.citations,
        overall_confidence=overall_confidence,
        correction_passes=state["retry_count"],
        llm_used=state["llm_used"],
        from_cache=state["from_cache"],
    )

    trace = TraceEntry(node="briefer", note=f"brief v{next_version} persisted")
    return {"final": brief, "trace": [*state["trace"], trace]}
