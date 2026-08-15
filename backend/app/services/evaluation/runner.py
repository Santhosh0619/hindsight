import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.critic_agent import judge_verification
from app.core.config import get_settings
from app.core.errors import LLMUnavailableError, ValidationAppError
from app.core.logging import get_logger
from app.models.evaluation import EvalCase, EvalCaseResult, EvalRun
from app.models.postmortem import FactType, Postmortem, PostmortemChunk, PostmortemFact
from app.schemas.incident import (
    Citation,
    DraftBrief,
    Hypothesis,
    NormalizedSignal,
    RunbookStepDraft,
)
from app.schemas.postmortem import PostmortemOut
from app.schemas.search import ChunkExcerptOut, SearchResponseOut, SearchResultOut, SourceHitOut
from app.services.evaluation.metrics import (
    citation_validity,
    rank_of_first_hit,
    recall_at_k,
    reciprocal_rank,
)
from app.services.graph_store import GraphStore
from app.services.ingestion.embed import embed
from app.services.llm.router import LLMRouter
from app.services.retrieval.fusion import reciprocal_rank_fusion
from app.services.retrieval.graph import search_graph
from app.services.retrieval.hybrid import best_hit_per_postmortem, ranked_ids
from app.services.retrieval.keyword import search_keyword
from app.services.retrieval.vector import search_vector

logger = get_logger(__name__)

AblationMode = Literal["vector", "vector_bm25", "full"]
ABLATION_MODES: tuple[AblationMode, ...] = ("vector", "vector_bm25", "full")
DEFAULT_TOP_K = 10
_RECALL_K = 5


async def _retrieve_ranked_ids(
    db: AsyncSession,
    graph_store: GraphStore,
    *,
    workspace_id: uuid.UUID,
    query: str,
    mode: AblationMode,
    top_k: int,
) -> list[uuid.UUID]:
    """Composes Phase 7's own retrieval primitives per ablation mode -- vector alone,
    vector+keyword, or vector+keyword+graph -- the same fusion `hybrid_search` runs for
    live search, just with the retriever subset selected by mode instead of hardcoded
    to all three. Not run concurrently: eval isn't latency-sensitive the way live search
    is, so sharing the caller's one session is simpler and safe (unlike hybrid.py's
    concurrent gather, which needs its own sessions per ADR 0007 §1)."""
    ranked_lists: dict[str, list[uuid.UUID]] = {}

    query_embedding = (await embed([query]))[0]
    vector_hits = await search_vector(
        db, workspace_id=workspace_id, query_embedding=query_embedding, top_k=top_k
    )
    if vector_hits:
        ranked_lists["vector"] = ranked_ids(best_hit_per_postmortem(vector_hits))

    if mode in ("vector_bm25", "full"):
        keyword_hits = await search_keyword(db, workspace_id=workspace_id, query=query, top_k=top_k)
        if keyword_hits:
            ranked_lists["keyword"] = ranked_ids(best_hit_per_postmortem(keyword_hits))

    if mode == "full":
        graph_hits = await search_graph(
            db, graph_store, workspace_id=workspace_id, query=query, top_k=top_k
        )
        if graph_hits:
            ranked_lists["graph"] = ranked_ids(best_hit_per_postmortem(graph_hits))

    settings = get_settings()
    fused = reciprocal_rank_fusion(ranked_lists, k=settings.rrf_k)
    return sorted(fused, key=lambda pid: fused[pid], reverse=True)[:top_k]


async def _stub_draft_brief(
    db: AsyncSession, *, top_postmortem_id: uuid.UUID
) -> tuple[DraftBrief, SearchResponseOut] | None:
    """Derives a minimal DraftBrief from the top-matched postmortem's own extracted
    facts -- the same root_cause/remediation -> hypothesis/runbook_step shape
    app/seed/seed.py's `_precompute_brief` already established -- so citation_validity
    can be scored deterministically, with no LLM call. Returns None if the postmortem
    has no facts to cite (nothing to validate)."""
    postmortem_result = await db.execute(
        select(Postmortem).where(Postmortem.id == top_postmortem_id)
    )
    postmortem = postmortem_result.scalar_one_or_none()
    if postmortem is None:
        return None

    facts_result = await db.execute(
        select(PostmortemFact, PostmortemChunk)
        .join(PostmortemChunk, PostmortemChunk.id == PostmortemFact.source_chunk_id)
        .where(PostmortemFact.postmortem_id == top_postmortem_id)
    )
    fact_rows = facts_result.all()
    if not fact_rows:
        return None

    root_cause = next((f for f, c in fact_rows if f.fact_type == FactType.ROOT_CAUSE), None)
    remediation = next((f for f, c in fact_rows if f.fact_type == FactType.REMEDIATION), None)
    if root_cause is None and remediation is None:
        return None

    hypotheses: list[Hypothesis] = []
    runbook_steps: list[RunbookStepDraft] = []
    citations: list[Citation] = []
    results: list[SearchResultOut] = []
    postmortem_out = PostmortemOut.model_validate(postmortem)

    if root_cause is not None:
        chunk = next(c for f, c in fact_rows if f is root_cause)
        citation = Citation(chunk_id=chunk.id, postmortem_id=top_postmortem_id, quote=None)
        citations.append(citation)
        hypotheses.append(
            Hypothesis(statement=root_cause.statement, confidence=0.8, citations=[citation])
        )
        results.append(
            SearchResultOut(
                postmortem=postmortem_out,
                score=1.0,
                sources=[SourceHitOut(source="vector", rank=1, raw_score=0.0)],
                chunk_excerpt=ChunkExcerptOut(
                    chunk_id=chunk.id, section_label=chunk.section_label, content=chunk.content
                ),
                graph_reason=None,
            )
        )

    if remediation is not None:
        chunk = next(c for f, c in fact_rows if f is remediation)
        citation = Citation(chunk_id=chunk.id, postmortem_id=top_postmortem_id, quote=None)
        citations.append(citation)
        runbook_steps.append(
            RunbookStepDraft(
                step=remediation.statement,
                source_postmortem_id=top_postmortem_id,
                citation=citation,
            )
        )
        results.append(
            SearchResultOut(
                postmortem=postmortem_out,
                score=1.0,
                sources=[SourceHitOut(source="vector", rank=1, raw_score=0.0)],
                chunk_excerpt=ChunkExcerptOut(
                    chunk_id=chunk.id, section_label=chunk.section_label, content=chunk.content
                ),
                graph_reason=None,
            )
        )

    draft = DraftBrief(hypotheses=hypotheses, runbook_steps=runbook_steps, citations=citations)
    retrieval = SearchResponseOut(results=results, mode="hybrid", timings_ms={})
    return draft, retrieval


async def _groundedness(
    router: LLMRouter, *, incident_text: str, draft: DraftBrief
) -> float | None:
    signal = NormalizedSignal(
        symptoms=[incident_text],
        error_strings=[],
        metrics={},
        affected_service_ids=[],
        unresolved_mentions=[],
        time_window=None,
        severity_guess=None,
        extracted_by_model=None,
        extraction_confidence=None,
    )
    try:
        judgment = await judge_verification(router, signal=signal, draft=draft)
    except LLMUnavailableError as exc:
        logger.warning("eval_groundedness_skipped", error=str(exc))
        return None
    return judgment.score


@dataclass
class _CaseScore:
    eval_case_id: uuid.UUID
    retrieved_ids: list[uuid.UUID]
    rank_of_first_hit: int | None
    citation_validity: float | None
    groundedness: float | None
    passed: bool


async def _case_result(
    db: AsyncSession,
    graph_store: GraphStore,
    router: LLMRouter,
    *,
    workspace_id: uuid.UUID,
    case: EvalCase,
    mode: AblationMode,
    top_k: int,
    llm_configured: bool,
) -> _CaseScore:
    retrieved_ids = await _retrieve_ranked_ids(
        db, graph_store, workspace_id=workspace_id, query=case.incident_text, mode=mode, top_k=top_k
    )
    expected_ids = set(case.expected_postmortem_ids)
    rank = rank_of_first_hit(retrieved_ids, expected_ids)

    case_citation_validity: float | None = None
    case_groundedness: float | None = None
    if retrieved_ids:
        stub = await _stub_draft_brief(db, top_postmortem_id=retrieved_ids[0])
        if stub is not None:
            draft, retrieval = stub
            case_citation_validity = citation_validity(draft, retrieval)
            if llm_configured:
                case_groundedness = await _groundedness(
                    router, incident_text=case.incident_text, draft=draft
                )

    logger.debug(
        "eval_case_scored",
        case_name=case.name,
        rank_of_first_hit=rank,
        citation_validity=case_citation_validity,
        groundedness=case_groundedness,
    )
    return _CaseScore(
        eval_case_id=case.id,
        retrieved_ids=retrieved_ids,
        rank_of_first_hit=rank,
        citation_validity=case_citation_validity,
        groundedness=case_groundedness,
        passed=recall_at_k(rank, _RECALL_K),
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


async def run_eval(
    db: AsyncSession,
    graph_store: GraphStore,
    router: LLMRouter,
    *,
    workspace_id: uuid.UUID,
    mode: AblationMode,
    top_k: int = DEFAULT_TOP_K,
    llm_configured: bool,
) -> EvalRun:
    started_at = datetime.now(UTC)

    cases_result = await db.execute(select(EvalCase).where(EvalCase.workspace_id == workspace_id))
    cases = list(cases_result.scalars().all())
    if not cases:
        raise ValidationAppError("No eval cases found for this workspace -- run `make seed` first")

    logger.info(
        "eval_run_started", workspace_id=str(workspace_id), mode=mode, case_count=len(cases)
    )

    recalls_1: list[float] = []
    recalls_5: list[float] = []
    reciprocal_ranks: list[float] = []
    citation_validities: list[float] = []
    groundedness_scores: list[float] = []
    scores: list[_CaseScore] = []

    for case in cases:
        score = await _case_result(
            db,
            graph_store,
            router,
            workspace_id=workspace_id,
            case=case,
            mode=mode,
            top_k=top_k,
            llm_configured=llm_configured,
        )
        scores.append(score)
        recalls_1.append(1.0 if recall_at_k(score.rank_of_first_hit, 1) else 0.0)
        recalls_5.append(1.0 if recall_at_k(score.rank_of_first_hit, _RECALL_K) else 0.0)
        reciprocal_ranks.append(reciprocal_rank(score.rank_of_first_hit))
        if score.citation_validity is not None:
            citation_validities.append(score.citation_validity)
        if score.groundedness is not None:
            groundedness_scores.append(score.groundedness)

    finished_at = datetime.now(UTC)
    eval_run = EvalRun(
        workspace_id=workspace_id,
        mode=mode,
        started_at=started_at,
        finished_at=finished_at,
        recall_at_1=_mean(recalls_1),
        recall_at_5=_mean(recalls_5),
        mrr=_mean(reciprocal_ranks),
        groundedness=_mean(groundedness_scores),
        citation_validity=_mean(citation_validities),
        cases_run=len(cases),
    )
    db.add(eval_run)
    await db.flush()

    for score in scores:
        db.add(
            EvalCaseResult(
                eval_run_id=eval_run.id,
                eval_case_id=score.eval_case_id,
                retrieved_ids=score.retrieved_ids,
                rank_of_first_hit=score.rank_of_first_hit,
                groundedness=score.groundedness,
                passed=score.passed,
            )
        )
    await db.commit()
    await db.refresh(eval_run)

    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    logger.info(
        "eval_run_completed",
        workspace_id=str(workspace_id),
        mode=mode,
        recall_at_1=eval_run.recall_at_1,
        recall_at_5=eval_run.recall_at_5,
        mrr=eval_run.mrr,
        citation_validity=eval_run.citation_validity,
        groundedness=eval_run.groundedness,
        duration_ms=duration_ms,
    )
    return eval_run
