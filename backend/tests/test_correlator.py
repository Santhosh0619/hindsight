import uuid
from datetime import UTC, datetime, timedelta

from app.agents.correlator import score_candidates
from app.models.postmortem import PostmortemStatus
from app.schemas.postmortem import PostmortemOut
from app.schemas.search import SearchResponseOut, SearchResultOut, SourceHitOut

_NOW = datetime.now(UTC)


def _postmortem(*, occurred_at: datetime | None, created_at: datetime) -> PostmortemOut:
    return PostmortemOut(
        id=uuid.uuid4(),
        external_ref=None,
        title="pm",
        occurred_at=occurred_at,
        duration_minutes=None,
        severity=None,
        status=PostmortemStatus.INDEXED,
        injection_flagged=False,
        failure_reason=None,
        created_at=created_at,
    )


def test_score_candidates_computes_expected_subscores_and_rank() -> None:
    recent = _postmortem(occurred_at=_NOW, created_at=_NOW)
    old = _postmortem(occurred_at=None, created_at=_NOW - timedelta(days=200))

    retrieval = SearchResponseOut(
        mode="hybrid",
        timings_ms={},
        results=[
            SearchResultOut(
                postmortem=recent,
                score=0.9,
                sources=[
                    SourceHitOut(source="vector", rank=1, raw_score=0.2),  # distance
                    SourceHitOut(source="keyword", rank=1, raw_score=3.0),  # bm25
                ],
                chunk_excerpt=None,
                graph_reason=None,
            ),
            SearchResultOut(
                postmortem=old,
                score=0.4,
                sources=[SourceHitOut(source="graph", rank=1, raw_score=0.6)],
                chunk_excerpt=None,
                graph_reason=None,
            ),
        ],
    )
    failure_mode_labels = {
        recent.id: {"deployment_failure"},
        old.id: {"deployment_failure", "capacity_exhaustion"},
    }

    candidates = score_candidates(retrieval, failure_mode_labels_by_postmortem=failure_mode_labels)

    by_id = {c.postmortem_id: c for c in candidates}
    recent_match = by_id[recent.id]
    old_match = by_id[old.id]

    assert recent_match.vector_score == 0.8  # 1 - 0.2
    assert recent_match.keyword_score == 0.75  # 3 / (3 + 1)
    assert recent_match.graph_score == 0.0
    assert recent_match.failure_mode_overlap == 1.0  # deployment_failure in both -> freq 1.0
    assert recent_match.recency == 1.0  # occurred today

    assert old_match.vector_score == 0.0
    assert old_match.keyword_score == 0.0
    assert old_match.graph_score == 0.6
    assert old_match.failure_mode_overlap == 0.75  # mean(freq(1.0), freq(0.5))
    assert old_match.recency == 0.2  # older than the 180-day window, floored

    # Recent candidate's higher overall_score ranks it first.
    assert recent_match.overall_score > old_match.overall_score
    assert recent_match.rank == 1
    assert old_match.rank == 2


def test_score_candidates_on_an_empty_retrieval_returns_no_candidates() -> None:
    retrieval = SearchResponseOut(mode="hybrid", timings_ms={}, results=[])
    assert score_candidates(retrieval, failure_mode_labels_by_postmortem={}) == []


def test_a_candidate_with_no_failure_modes_gets_zero_overlap() -> None:
    postmortem = _postmortem(occurred_at=_NOW, created_at=_NOW)
    retrieval = SearchResponseOut(
        mode="vector",
        timings_ms={},
        results=[
            SearchResultOut(
                postmortem=postmortem,
                score=0.5,
                sources=[SourceHitOut(source="vector", rank=1, raw_score=0.5)],
                chunk_excerpt=None,
                graph_reason=None,
            )
        ],
    )
    candidates = score_candidates(retrieval, failure_mode_labels_by_postmortem={})
    assert candidates[0].failure_mode_overlap == 0.0
