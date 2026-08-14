import uuid

from app.schemas.incident import CandidateMatch
from app.schemas.search import SearchResponseOut, SourceHitOut, SourceName
from app.services.retrieval.graph import recency_weight

_SUBSCORE_COUNT = 5


def _source_score(result_sources: list[SourceHitOut], source: SourceName) -> float | None:
    for hit in result_sources:
        if hit.source == source:
            return hit.raw_score
    return None


def score_candidates(
    retrieval: SearchResponseOut,
    *,
    failure_mode_labels_by_postmortem: dict[uuid.UUID, set[str]],
) -> list[CandidateMatch]:
    """Pure, deterministic, no I/O -- everything correlator_node needs is passed in.

    failure_mode_overlap is a recurrence signal among the candidates themselves (see
    FRD Gap #3): the mean frequency, across this whole candidate set, of each
    candidate's own failure-mode labels. A candidate whose failure modes are also
    common among the other retrieved candidates scores higher.
    """
    label_frequency: dict[str, float] = {}
    total = len(retrieval.results)
    if total > 0:
        label_counts: dict[str, int] = {}
        for result in retrieval.results:
            labels = failure_mode_labels_by_postmortem.get(result.postmortem.id, set())
            for label in labels:
                label_counts[label] = label_counts.get(label, 0) + 1
        label_frequency = {label: count / total for label, count in label_counts.items()}

    unranked: list[CandidateMatch] = []
    for result in retrieval.results:
        distance = _source_score(result.sources, "vector")
        vector_score = max(0.0, 1.0 - distance) if distance is not None else 0.0

        bm25 = _source_score(result.sources, "keyword")
        keyword_score = bm25 / (bm25 + 1.0) if bm25 is not None else 0.0

        graph_score = _source_score(result.sources, "graph") or 0.0

        labels = failure_mode_labels_by_postmortem.get(result.postmortem.id, set())
        failure_mode_overlap = (
            sum(label_frequency.get(label, 0.0) for label in labels) / len(labels)
            if labels
            else 0.0
        )

        recency = recency_weight(result.postmortem.occurred_at or result.postmortem.created_at)

        overall_score = (
            vector_score + keyword_score + graph_score + failure_mode_overlap + recency
        ) / _SUBSCORE_COUNT

        unranked.append(
            CandidateMatch(
                postmortem_id=result.postmortem.id,
                vector_score=vector_score,
                keyword_score=keyword_score,
                graph_score=graph_score,
                failure_mode_overlap=failure_mode_overlap,
                recency=recency,
                overall_score=overall_score,
                rank=0,
            )
        )

    ranked = sorted(unranked, key=lambda c: c.overall_score, reverse=True)
    return [c.model_copy(update={"rank": i + 1}) for i, c in enumerate(ranked)]
