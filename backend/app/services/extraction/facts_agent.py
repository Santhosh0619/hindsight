import uuid

from pydantic import BaseModel

from app.schemas.postmortem import PostmortemChunkOut
from app.services.extraction.prompting import UNTRUSTED_DATA_NOTICE, render_chunks_for_prompt
from app.services.llm.router import LLMRouter


class FactItem(BaseModel):
    statement: str
    chunk_id: uuid.UUID
    confidence: float | None = None


class ExtractedFacts(BaseModel):
    triggers: list[FactItem]
    root_causes: list[FactItem]
    remediations: list[FactItem]
    detection_gaps: list[FactItem]
    contributing_factors: list[FactItem]


_SYSTEM_PROMPT = (
    "You are an incident-postmortem analyst. Extract concrete facts from the "
    "provided postmortem excerpts, grouped into triggers, root causes, "
    "remediations, detection gaps, and contributing factors. Every fact must cite "
    "the exact chunk id it was drawn from -- never invent a chunk id, and never cite "
    "a chunk id that isn't present in the excerpts you were given."
)


async def extract_facts(router: LLMRouter, *, chunks: list[PostmortemChunkOut]) -> ExtractedFacts:
    prompt = f"{UNTRUSTED_DATA_NOTICE}\n\n{render_chunks_for_prompt(chunks)}"
    return await router.structured(prompt, system=_SYSTEM_PROMPT, result_type=ExtractedFacts)
