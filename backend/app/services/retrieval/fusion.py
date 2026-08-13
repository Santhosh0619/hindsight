import uuid


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[uuid.UUID]], *, k: int
) -> dict[uuid.UUID, float]:
    """score = Σ 1/(k + rank_i) across every source list a postmortem id appears in.

    A single-list call (one key in ranked_lists) is mathematically equivalent to that
    list's own rank order -- 1/(k+rank) is monotonic in rank -- just expressed on the
    same score scale a multi-source fused result uses, so single-mode search results
    carry a comparable `score` field without a separate scoring path.
    """
    scores: dict[uuid.UUID, float] = {}
    for ranked_ids in ranked_lists.values():
        for rank, postmortem_id in enumerate(ranked_ids, start=1):
            scores[postmortem_id] = scores.get(postmortem_id, 0.0) + 1.0 / (k + rank)
    return scores
