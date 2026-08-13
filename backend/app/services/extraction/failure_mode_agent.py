from pydantic import BaseModel

from app.schemas.postmortem import PostmortemChunkOut
from app.services.extraction.prompting import UNTRUSTED_DATA_NOTICE, render_chunks_for_prompt
from app.services.extraction.taxonomy import FailureModeFamily
from app.services.llm.router import LLMRouter


class FailureModeClassification(BaseModel):
    family: FailureModeFamily
    confidence: float


class FailureModeClassificationResult(BaseModel):
    classifications: list[FailureModeClassification]


_FAMILY_LIST = ", ".join(family.value for family in FailureModeFamily)

_SYSTEM_PROMPT = (
    "You are an incident-postmortem analyst. Classify the incident described in the "
    f"provided postmortem excerpts against this fixed taxonomy: {_FAMILY_LIST}. "
    "A postmortem may match more than one family. Only use families from this list."
)


async def classify_failure_modes(
    router: LLMRouter, *, chunks: list[PostmortemChunkOut]
) -> FailureModeClassificationResult:
    prompt = f"{UNTRUSTED_DATA_NOTICE}\n\n{render_chunks_for_prompt(chunks)}"
    return await router.structured(
        prompt, system=_SYSTEM_PROMPT, result_type=FailureModeClassificationResult
    )
