from app.schemas.incident import CandidateMatch, DraftBrief, NormalizedSignal
from app.schemas.search import SearchResponseOut
from app.services.extraction.prompting import UNTRUSTED_DATA_NOTICE
from app.services.llm.router import LLMRouter

SYSTEM_PROMPT = (
    "You are an incident-response analyst. Given a normalized incident signal and a "
    "ranked list of candidate prior postmortems (each with an excerpt and a chunk id), "
    "produce ranked hypotheses about what is happening, each with a confidence and at "
    "least one citation to a chunk id from the excerpts you were given. Also produce "
    "runbook steps drawn from the postmortems' remediations, each attributed to a "
    "chunk id when possible. Never cite a chunk id that wasn't shown to you, and never "
    "invent a fact not supported by the excerpts or the incident signal."
)


def _render_signal(signal: NormalizedSignal) -> str:
    lines = [
        f"Symptoms: {', '.join(signal.symptoms) or '(none extracted)'}",
        f"Error strings: {', '.join(signal.error_strings) or '(none)'}",
        f"Severity guess: {signal.severity_guess.value if signal.severity_guess else 'unknown'}",
    ]
    return "\n".join(lines)


def _render_candidates(candidates: list[CandidateMatch], retrieval: SearchResponseOut) -> str:
    result_by_postmortem = {r.postmortem.id: r for r in retrieval.results}
    blocks = []
    for candidate in candidates:
        result = result_by_postmortem.get(candidate.postmortem_id)
        if result is None or result.chunk_excerpt is None:
            continue
        blocks.append(
            f'<chunk id="{result.chunk_excerpt.chunk_id}" postmortem="{result.postmortem.title}" '
            f'overall_score="{candidate.overall_score:.2f}">\n{result.chunk_excerpt.content}\n</chunk>'
        )
    return "\n".join(blocks)


def render_prompt(
    *, signal: NormalizedSignal, candidates: list[CandidateMatch], retrieval: SearchResponseOut
) -> str:
    return (
        f"{UNTRUSTED_DATA_NOTICE}\n\n"
        f"{_render_signal(signal)}\n\n"
        f"{_render_candidates(candidates, retrieval)}"
    )


async def draft_brief(router: LLMRouter, *, prompt: str) -> DraftBrief:
    return await router.structured(prompt, system=SYSTEM_PROMPT, result_type=DraftBrief)
