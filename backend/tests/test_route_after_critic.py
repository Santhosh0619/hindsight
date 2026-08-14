import uuid

import pytest

from app.agents.edges import route_after_critic
from app.agents.state import initial_state
from app.schemas.incident import VerificationResult


def _state_with(*, llm_used: bool, retry_count: int, verification: VerificationResult | None):
    state = initial_state(incident_id=uuid.uuid4(), workspace_id=uuid.uuid4(), raw_text="alert")
    state["llm_used"] = llm_used
    state["retry_count"] = retry_count
    state["verification"] = verification
    return state


def _verification(score: float) -> VerificationResult:
    return VerificationResult(
        score=score, is_grounded=score >= 0.7, issues=[], suggested_refinements=["try again"]
    )


@pytest.mark.parametrize(
    ("score", "retry_count", "llm_used", "expected"),
    [
        (0.9, 0, True, "briefer"),  # high score -> done regardless of retries left
        (0.5, 0, True, "retriever"),  # low score, retries available -> retry
        (0.5, 1, True, "retriever"),  # still below max_correction_passes (2)
        (0.5, 2, True, "briefer"),  # retries exhausted -> briefer even though score is low
        (0.69, 0, True, "retriever"),  # just under threshold (0.7)
        (0.7, 0, True, "briefer"),  # exactly at threshold -> not "less than", so briefer
        (0.1, 0, False, "briefer"),  # no LLM -> never retry regardless of score
    ],
)
def test_route_after_critic_truth_table(
    score: float, retry_count: int, llm_used: bool, expected: str
) -> None:
    state = _state_with(
        llm_used=llm_used, retry_count=retry_count, verification=_verification(score)
    )
    assert route_after_critic(state) == expected
