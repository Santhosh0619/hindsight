import uuid
from datetime import UTC, datetime

from app.agents.citation_check import validate_citations
from app.models.postmortem import PostmortemStatus
from app.schemas.incident import Citation, DraftBrief, Hypothesis, RunbookStepDraft
from app.schemas.postmortem import PostmortemOut
from app.schemas.search import ChunkExcerptOut, SearchResponseOut, SearchResultOut


def _retrieval_with_one_chunk(
    chunk_id: uuid.UUID, content: str
) -> tuple[SearchResponseOut, uuid.UUID]:
    postmortem = PostmortemOut(
        id=uuid.uuid4(),
        external_ref=None,
        title="pm",
        occurred_at=None,
        duration_minutes=None,
        severity=None,
        status=PostmortemStatus.INDEXED,
        injection_flagged=False,
        failure_reason=None,
        created_at=datetime.now(UTC),
    )
    retrieval = SearchResponseOut(
        mode="hybrid",
        timings_ms={},
        results=[
            SearchResultOut(
                postmortem=postmortem,
                score=1.0,
                sources=[],
                chunk_excerpt=ChunkExcerptOut(
                    chunk_id=chunk_id, section_label=None, content=content
                ),
                graph_reason=None,
            )
        ],
    )
    return retrieval, postmortem.id


def test_a_citation_naming_a_chunk_id_outside_the_retrieval_set_always_fails() -> None:
    real_chunk_id = uuid.uuid4()
    retrieval, _real_postmortem_id = _retrieval_with_one_chunk(
        real_chunk_id, "The database connection pool was exhausted during peak traffic."
    )
    # This citation's chunk_id isn't in the retrieval at all, so there's nothing to
    # correct it against -- postmortem_id passes through unchanged, same as before.
    fabricated_citation = Citation(chunk_id=uuid.uuid4(), postmortem_id=uuid.uuid4())
    draft = DraftBrief(
        hypotheses=[
            Hypothesis(
                statement="Connection pool exhaustion caused the outage",
                confidence=0.8,
                citations=[fabricated_citation],
            )
        ],
        runbook_steps=[],
        citations=[fabricated_citation],
    )

    cleaned, invalid = validate_citations(draft, retrieval)

    assert cleaned.hypotheses == []  # the only hypothesis lost its only citation
    assert invalid == [fabricated_citation]


def test_a_citation_to_a_real_chunk_with_no_shared_terms_fails_plausibility() -> None:
    real_chunk_id = uuid.uuid4()
    retrieval, real_postmortem_id = _retrieval_with_one_chunk(
        real_chunk_id, "The database connection pool was exhausted during peak traffic."
    )
    # postmortem_id is deliberately wrong here too -- the analyst prompt never shows
    # the model a postmortem's real id (see citation_check.py's own comment), so a
    # citation this test constructs to look like model output should have the same
    # kind of wrong id a real model produces, and the fix corrects it regardless of
    # whether the citation ends up valid or invalid.
    unrelated_citation = Citation(chunk_id=real_chunk_id, postmortem_id=uuid.uuid4())
    draft = DraftBrief(
        hypotheses=[
            Hypothesis(
                statement="Something about widgets entirely",
                confidence=0.5,
                citations=[unrelated_citation],
            )
        ],
        runbook_steps=[],
        citations=[unrelated_citation],
    )

    cleaned, invalid = validate_citations(draft, retrieval)

    assert cleaned.hypotheses == []
    assert invalid == [unrelated_citation.model_copy(update={"postmortem_id": real_postmortem_id})]


def test_a_grounded_citation_survives() -> None:
    real_chunk_id = uuid.uuid4()
    retrieval, real_postmortem_id = _retrieval_with_one_chunk(
        real_chunk_id, "The database connection pool was exhausted during peak traffic."
    )
    # Same deliberately-wrong postmortem_id as the test above -- surviving a citation
    # doesn't mean trusting its postmortem_id either; the corrected value should win
    # even on the happy path.
    grounded_citation = Citation(chunk_id=real_chunk_id, postmortem_id=uuid.uuid4())
    draft = DraftBrief(
        hypotheses=[
            Hypothesis(
                statement="Connection pool exhaustion caused the outage",
                confidence=0.8,
                citations=[grounded_citation],
            )
        ],
        runbook_steps=[],
        citations=[grounded_citation],
    )

    cleaned, invalid = validate_citations(draft, retrieval)

    assert len(cleaned.hypotheses) == 1
    assert cleaned.hypotheses[0].citations == [
        grounded_citation.model_copy(update={"postmortem_id": real_postmortem_id})
    ]
    assert invalid == []


def test_an_invalid_runbook_step_citation_is_nulled_not_dropped() -> None:
    real_chunk_id = uuid.uuid4()
    retrieval, _real_postmortem_id = _retrieval_with_one_chunk(
        real_chunk_id, "The database connection pool was exhausted during peak traffic."
    )
    bad_citation = Citation(chunk_id=uuid.uuid4(), postmortem_id=uuid.uuid4())
    draft = DraftBrief(
        hypotheses=[],
        runbook_steps=[RunbookStepDraft(step="Restart the pool manager", citation=bad_citation)],
        citations=[],
    )

    cleaned, invalid = validate_citations(draft, retrieval)

    assert cleaned.runbook_steps[0].citation is None
    assert cleaned.runbook_steps[0].step == "Restart the pool manager"
    assert invalid == [bad_citation]
