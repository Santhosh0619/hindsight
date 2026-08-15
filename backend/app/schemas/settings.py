from typing import Literal

from pydantic import BaseModel

ProviderName = Literal["gemini", "groq", "ollama"]


class LLMProviderTestOut(BaseModel):
    provider: ProviderName
    configured: bool
    ok: bool | None
    latency_ms: int | None
    error: str | None
