from app.schemas.incident import IncidentSignalOut
from app.services.extraction.prompting import UNTRUSTED_DATA_NOTICE
from app.services.llm.router import LLMRouter

_SYSTEM_PROMPT = (
    "You are an incident-triage analyst. Read the provided raw alert text and extract "
    "a structured signal: symptoms observed, exact error strings, any numeric metrics "
    "mentioned, service names that seem involved (as plain names, not ids -- you don't "
    "know the real catalog), a time window if one is stated or implied, and your best "
    "guess at severity (sev1 = worst). Never invent a symptom, error string, or service "
    "name that isn't actually present in the alert text."
)


async def extract_signal(router: LLMRouter, *, raw_text: str) -> IncidentSignalOut:
    prompt = f'{UNTRUSTED_DATA_NOTICE}\n\n<chunk id="alert">\n{raw_text}\n</chunk>'
    return await router.structured(prompt, system=_SYSTEM_PROMPT, result_type=IncidentSignalOut)
