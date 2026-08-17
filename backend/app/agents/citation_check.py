import re
import uuid

from app.schemas.incident import Citation, DraftBrief, Hypothesis, RunbookStepDraft
from app.schemas.search import SearchResponseOut

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LENGTH = 4


def _key_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_PATTERN.findall(text.lower()) if len(t) >= _MIN_TOKEN_LENGTH}


def _is_plausible(statement: str, chunk_content: str) -> bool:
    claim_tokens = _key_tokens(statement)
    if not claim_tokens:
        return True  # nothing specific enough to check against -- not a failure
    chunk_tokens = _key_tokens(chunk_content)
    return not claim_tokens.isdisjoint(chunk_tokens)


def validate_citations(
    draft: DraftBrief, retrieval: SearchResponseOut
) -> tuple[DraftBrief, list[Citation]]:
    """Deterministic citation gate -- a citation fails if its chunk_id was never
    actually shown to the analyst, or if none of the claim's key terms appear in that
    chunk's content. A hard fail regardless of what an LLM judge would think (FR-05)."""
    chunk_content_by_id: dict[uuid.UUID, str] = {
        r.chunk_excerpt.chunk_id: r.chunk_excerpt.content
        for r in retrieval.results
        if r.chunk_excerpt is not None
    }
    # The analyst prompt only ever shows the model a chunk's postmortem *title*
    # (analyst_agent.py's <chunk postmortem="{title}">), never its id, so a citation's
    # own postmortem_id field is never a value the model could have reliably known --
    # observed defaulting to an all-zero placeholder UUID in practice. Re-derive it here
    # from the retrieval results (a fact the server already has) before it's used for
    # anything, most importantly retriever_node's retry-exclusion set, which would
    # otherwise silently exclude nothing on every corrective pass.
    postmortem_id_by_chunk_id: dict[uuid.UUID, uuid.UUID] = {
        r.chunk_excerpt.chunk_id: r.postmortem.id
        for r in retrieval.results
        if r.chunk_excerpt is not None
    }

    invalid: list[Citation] = []

    def _corrected(citation: Citation) -> Citation:
        real_postmortem_id = postmortem_id_by_chunk_id.get(citation.chunk_id)
        if real_postmortem_id is None or real_postmortem_id == citation.postmortem_id:
            return citation
        return citation.model_copy(update={"postmortem_id": real_postmortem_id})

    def _citation_is_valid(citation: Citation, statement: str) -> bool:
        content = chunk_content_by_id.get(citation.chunk_id)
        if content is None:
            invalid.append(_corrected(citation))
            return False
        if not _is_plausible(statement, content):
            invalid.append(_corrected(citation))
            return False
        return True

    surviving_hypotheses: list[Hypothesis] = []
    for hypothesis in draft.hypotheses:
        kept_citations = [
            _corrected(c)
            for c in hypothesis.citations
            if _citation_is_valid(c, hypothesis.statement)
        ]
        if kept_citations:
            surviving_hypotheses.append(hypothesis.model_copy(update={"citations": kept_citations}))

    cleaned_steps: list[RunbookStepDraft] = []
    for step in draft.runbook_steps:
        if step.citation is None:
            cleaned_steps.append(step)
        elif not _citation_is_valid(step.citation, step.step):
            cleaned_steps.append(step.model_copy(update={"citation": None}))
        else:
            cleaned_steps.append(step.model_copy(update={"citation": _corrected(step.citation)}))

    all_citations = [c for h in surviving_hypotheses for c in h.citations]
    cleaned = DraftBrief(
        hypotheses=surviving_hypotheses, runbook_steps=cleaned_steps, citations=all_citations
    )
    return cleaned, invalid
