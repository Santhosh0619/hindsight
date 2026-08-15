import uuid
from datetime import UTC, datetime

from app.models.postmortem import PostmortemStatus
from app.schemas.incident import Citation, DraftBrief, Hypothesis, RunbookStepDraft
from app.schemas.postmortem import PostmortemOut
from app.schemas.search import ChunkExcerptOut, SearchResponseOut, SearchResultOut, SourceHitOut
from app.services.evaluation.metrics import (
    citation_validity,
    rank_of_first_hit,
    recall_at_k,
    reciprocal_rank,
)


def _ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def test_rank_of_first_hit_returns_one_based_rank_of_first_match() -> None:
    a, b, c = _ids(3)
    assert rank_of_first_hit([a, b, c], {c}) == 3
    assert rank_of_first_hit([a, b, c], {a, c}) == 1


def test_rank_of_first_hit_returns_none_when_nothing_matches() -> None:
    a, b = _ids(2)
    assert rank_of_first_hit([a, b], set()) is None
    assert rank_of_first_hit([], {a}) is None


def test_recall_at_k_true_only_within_k() -> None:
    assert recall_at_k(1, 5) is True
    assert recall_at_k(5, 5) is True
    assert recall_at_k(6, 5) is False
    assert recall_at_k(None, 5) is False


def test_reciprocal_rank() -> None:
    assert reciprocal_rank(1) == 1.0
    assert reciprocal_rank(4) == 0.25
    assert reciprocal_rank(None) == 0.0


def _postmortem_out() -> PostmortemOut:
    return PostmortemOut(
        id=uuid.uuid4(),
        external_ref=None,
        title="pm",
        occurred_at=None,
        duration_minutes=None,
        severity=None,
        status=PostmortemStatus.INDEXED,
        failure_reason=None,
        injection_flagged=False,
        created_at=datetime.now(UTC),
    )


def test_citation_validity_returns_none_when_draft_has_no_citations() -> None:
    draft = DraftBrief(hypotheses=[], runbook_steps=[], citations=[])
    retrieval = SearchResponseOut(results=[], mode="hybrid", timings_ms={})
    assert citation_validity(draft, retrieval) is None


def test_citation_validity_scores_a_fully_valid_draft_as_one() -> None:
    postmortem_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    citation = Citation(chunk_id=chunk_id, postmortem_id=postmortem_id, quote=None)
    draft = DraftBrief(
        hypotheses=[
            Hypothesis(
                statement="Connection pool exhaustion caused the outage.",
                confidence=0.8,
                citations=[citation],
            )
        ],
        runbook_steps=[],
        citations=[citation],
    )
    retrieval = SearchResponseOut(
        results=[
            SearchResultOut(
                postmortem=_postmortem_out(),
                score=1.0,
                sources=[SourceHitOut(source="vector", rank=1, raw_score=0.0)],
                chunk_excerpt=ChunkExcerptOut(
                    chunk_id=chunk_id,
                    section_label="Root Cause",
                    content="Connection pool exhaustion caused the outage during peak traffic.",
                ),
                graph_reason=None,
            )
        ],
        mode="hybrid",
        timings_ms={},
    )
    assert citation_validity(draft, retrieval) == 1.0


def test_citation_validity_penalizes_a_citation_to_a_chunk_never_shown() -> None:
    postmortem_id = uuid.uuid4()
    real_chunk_id = uuid.uuid4()
    fake_chunk_id = uuid.uuid4()
    real_citation = Citation(chunk_id=real_chunk_id, postmortem_id=postmortem_id, quote=None)
    fake_citation = Citation(chunk_id=fake_chunk_id, postmortem_id=postmortem_id, quote=None)
    draft = DraftBrief(
        hypotheses=[Hypothesis(statement="Real claim.", confidence=0.8, citations=[real_citation])],
        runbook_steps=[
            RunbookStepDraft(
                step="Do the thing.", source_postmortem_id=postmortem_id, citation=fake_citation
            )
        ],
        citations=[real_citation, fake_citation],
    )
    retrieval = SearchResponseOut(
        results=[
            SearchResultOut(
                postmortem=_postmortem_out(),
                score=1.0,
                sources=[SourceHitOut(source="vector", rank=1, raw_score=0.0)],
                chunk_excerpt=ChunkExcerptOut(
                    chunk_id=real_chunk_id, section_label="Root Cause", content="Real claim text."
                ),
                graph_reason=None,
            )
        ],
        mode="hybrid",
        timings_ms={},
    )
    assert citation_validity(draft, retrieval) == 0.5
