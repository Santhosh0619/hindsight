from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.errors import LLMUnavailableError
from app.core.logging import get_logger
from app.services.llm.gemini import GeminiProvider
from app.services.llm.groq import GroqLLMProvider
from app.services.llm.ollama import OllamaLLMProvider
from app.services.llm.provider import LLMProvider, LLMResponse, T

# _try_providers' own return type is unconstrained (unlike provider.py's T, which is
# bound to BaseModel for structured()'s result_type) -- structured_with_usage() calls
# it with a tuple[T, LLMResponse], which isn't itself a BaseModel.
R = TypeVar("R")

logger = get_logger(__name__)

# Retries within a single provider before the router moves on to the next one --
# bounded so a genuinely-down provider fails over in a fixed number of attempts
# rather than hanging the job.
_MAX_ATTEMPTS_PER_PROVIDER = 2


class LLMRouter:
    def __init__(self, providers: list[LLMProvider]) -> None:
        self._providers = providers

    async def complete(self, prompt: str, *, system: str) -> LLMResponse:
        return await self._try_providers(lambda p: p.complete(prompt, system=system))

    async def structured(self, prompt: str, *, system: str, result_type: type[T]) -> T:
        return await self._try_providers(
            lambda p: p.structured(prompt, system=system, result_type=result_type)
        )

    async def structured_with_usage(
        self, prompt: str, *, system: str, result_type: type[T]
    ) -> tuple[T, LLMResponse]:
        return await self._try_providers(
            lambda p: p.structured_with_usage(prompt, system=system, result_type=result_type)
        )

    async def _try_providers(self, call: Callable[[LLMProvider], Awaitable[R]]) -> R:
        errors: list[str] = []
        for provider in self._providers:
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(_MAX_ATTEMPTS_PER_PROVIDER),
                    wait=wait_exponential(multiplier=1, min=1, max=10),
                    reraise=True,
                ):
                    with attempt:
                        return await call(provider)
            except Exception as exc:  # noqa: BLE001 -- collected and re-raised as
                # LLMUnavailableError below; a provider failing is expected/handled,
                # not a bug to propagate raw.
                logger.warning("llm_provider_failed", provider=provider.model_name, error=str(exc))
                errors.append(f"{provider.model_name}: {exc}")
        raise LLMUnavailableError(
            "All LLM providers unavailable", detail={"providers_tried": errors}
        )


def build_router(settings: Settings) -> LLMRouter:
    providers: list[LLMProvider] = []
    if settings.llm_api_key:
        providers.append(GeminiProvider(api_key=settings.llm_api_key, model=settings.llm_model))
    if settings.groq_api_key:
        providers.append(GroqLLMProvider(api_key=settings.groq_api_key, model=settings.groq_model))
    providers.append(
        OllamaLLMProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
    )
    return LLMRouter(providers)
