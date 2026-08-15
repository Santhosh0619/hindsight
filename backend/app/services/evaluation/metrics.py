import uuid

from app.agents.citation_check import validate_citations
from app.schemas.incident import DraftBrief
from app.schemas.search import SearchResponseOut


def rank_of_first_hit(retrieved_ids: list[uuid.UUID], expected_ids: set[uuid.UUID]) -> int | None:
    """1-based rank of the first retrieved id that's also an expected match, or None if
    none of the retrieved ids are expected (including when nothing was retrieved at all,
    or when the case has no expected ids to match against)."""
    for rank, retrieved_id in enumerate(retrieved_ids, start=1):
        if retrieved_id in expected_ids:
            return rank
    return None


def recall_at_k(rank: int | None, k: int) -> bool:
    return rank is not None and rank <= k


def reciprocal_rank(rank: int | None) -> float:
    return 1.0 / rank if rank is not None else 0.0


def citation_validity(draft: DraftBrief, retrieval: SearchResponseOut) -> float | None:
    """Fraction of the draft's citations that survive the deterministic gate Phase 8
    already built (chunk_id was actually shown, and its content plausibly supports the
    claim). None if the draft carries no citations to score -- nothing to check is not
    the same as everything failing."""
    all_citations = [c for h in draft.hypotheses for c in h.citations] + [
        s.citation for s in draft.runbook_steps if s.citation is not None
    ]
    if not all_citations:
        return None
    _, invalid = validate_citations(draft, retrieval)
    return (len(all_citations) - len(invalid)) / len(all_citations)
