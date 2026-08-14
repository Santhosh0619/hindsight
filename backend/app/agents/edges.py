from typing import Literal

from app.agents.state import TriageState
from app.core.config import get_settings

RouteDecision = Literal["retriever", "briefer"]


def route_after_critic(state: TriageState) -> RouteDecision:
    if not state["llm_used"]:
        # Nothing to gain from retrying against a still-unavailable LLM.
        return "briefer"

    verification = state["verification"]
    assert verification is not None

    settings = get_settings()
    if (
        verification.score < settings.critic_threshold
        and state["retry_count"] < settings.max_correction_passes
    ):
        return "retriever"
    return "briefer"
