from pydantic import BaseModel

from app.models.postmortem import ServiceLinkRole
from app.schemas.postmortem import PostmortemChunkOut
from app.services.extraction.prompting import UNTRUSTED_DATA_NOTICE, render_chunks_for_prompt
from app.services.llm.router import LLMRouter


class ServiceLink(BaseModel):
    service_name: str
    role: ServiceLinkRole
    confidence: float | None = None


class ServiceLinkResult(BaseModel):
    links: list[ServiceLink]


_SYSTEM_PROMPT = (
    "You are an incident-postmortem analyst. Identify which known services this "
    "postmortem involves, and each one's role: root_cause, affected, or downstream. "
    "Only name services from the provided list of known service names -- never "
    "invent a service that isn't in that list."
)


async def link_services(
    router: LLMRouter, *, chunks: list[PostmortemChunkOut], known_service_names: list[str]
) -> ServiceLinkResult:
    services_block = "Known services in this workspace: " + ", ".join(known_service_names)
    prompt = f"{UNTRUSTED_DATA_NOTICE}\n\n{services_block}\n\n{render_chunks_for_prompt(chunks)}"
    return await router.structured(prompt, system=_SYSTEM_PROMPT, result_type=ServiceLinkResult)
