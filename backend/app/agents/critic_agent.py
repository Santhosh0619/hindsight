from app.schemas.incident import DraftBrief, LLMVerificationJudgment, NormalizedSignal
from app.services.extraction.prompting import UNTRUSTED_DATA_NOTICE
from app.services.llm.provider import LLMResponse
from app.services.llm.router import LLMRouter

_SYSTEM_PROMPT = (
    "You are a skeptical reviewer checking an incident brief for groundedness and "
    "completeness. The citations you see have already passed a mechanical check that "
    "every cited chunk id is real and plausibly related -- your job is judgment, not "
    "citation existence: does each hypothesis's confidence match the strength of its "
    "evidence, does the brief actually address the incident signal, and is anything "
    "important missing? Score from 0 (not usable) to 1 (fully grounded and complete). "
    "If you would lower the score, say what refinement to the search query would help."
)


def _render(signal: NormalizedSignal, draft: DraftBrief) -> str:
    hypothesis_lines = [
        f"- {h.statement} (confidence={h.confidence}, {len(h.citations)} citation(s))"
        for h in draft.hypotheses
    ]
    return (
        f"Incident symptoms: {', '.join(signal.symptoms) or '(none extracted)'}\n"
        f"Incident error strings: {', '.join(signal.error_strings) or '(none)'}\n\n"
        f"Draft hypotheses:\n" + ("\n".join(hypothesis_lines) or "(none)")
    )


async def judge_verification(
    router: LLMRouter, *, signal: NormalizedSignal, draft: DraftBrief
) -> LLMVerificationJudgment:
    prompt = f"{UNTRUSTED_DATA_NOTICE}\n\n{_render(signal, draft)}"
    return await router.structured(
        prompt, system=_SYSTEM_PROMPT, result_type=LLMVerificationJudgment
    )


async def judge_verification_with_usage(
    router: LLMRouter, *, signal: NormalizedSignal, draft: DraftBrief
) -> tuple[LLMVerificationJudgment, LLMResponse]:
    """Same call as `judge_verification`, plus token usage -- a separate function
    rather than changing `judge_verification`'s own return shape, since Phase 12's
    evaluation harness (`app/services/evaluation/runner.py`) already calls it expecting
    a bare `LLMVerificationJudgment` and has no use for per-node token tracking."""
    prompt = f"{UNTRUSTED_DATA_NOTICE}\n\n{_render(signal, draft)}"
    return await router.structured_with_usage(
        prompt, system=_SYSTEM_PROMPT, result_type=LLMVerificationJudgment
    )
