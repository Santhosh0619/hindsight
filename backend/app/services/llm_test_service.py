import time

from app.core.config import Settings
from app.schemas.settings import LLMProviderTestOut, ProviderName
from app.services.llm.gemini import GeminiProvider
from app.services.llm.groq import GroqLLMProvider
from app.services.llm.ollama import OllamaLLMProvider
from app.services.llm.provider import LLMProvider

_TEST_PROMPT = "Reply with the single word: ok"
_TEST_SYSTEM = "You are a connectivity check. Follow the instruction exactly."


async def _test_provider(provider: LLMProvider) -> tuple[bool, int, str | None]:
    start = time.monotonic()
    try:
        await provider.complete(_TEST_PROMPT, system=_TEST_SYSTEM)
    except Exception as exc:  # noqa: BLE001 -- a failed connectivity check is the
        # entire point of this endpoint's response, not an error to propagate.
        latency_ms = int((time.monotonic() - start) * 1000)
        return False, latency_ms, str(exc)
    latency_ms = int((time.monotonic() - start) * 1000)
    return True, latency_ms, None


async def test_all_providers(settings: Settings) -> list[LLMProviderTestOut]:
    """Tests each of the three provider slots directly, never through LLMRouter's
    fallback chain -- routing through the router would hide which specific provider
    actually answered, defeating the point of a per-provider diagnostic."""
    results: list[LLMProviderTestOut] = []

    slots: list[tuple[ProviderName, LLMProvider | None]] = [
        (
            "gemini",
            GeminiProvider(api_key=settings.llm_api_key, model=settings.llm_model)
            if settings.llm_api_key
            else None,
        ),
        (
            "groq",
            GroqLLMProvider(api_key=settings.groq_api_key, model=settings.groq_model)
            if settings.groq_api_key
            else None,
        ),
        # Ollama needs no key -- "configured" always true, but reachability (ok) can
        # still be false if nothing is listening at ollama_base_url.
        (
            "ollama",
            OllamaLLMProvider(base_url=settings.ollama_base_url, model=settings.ollama_model),
        ),
    ]

    for name, provider in slots:
        if provider is None:
            results.append(
                LLMProviderTestOut(
                    provider=name, configured=False, ok=None, latency_ms=None, error=None
                )
            )
            continue
        ok, latency_ms, error = await _test_provider(provider)
        results.append(
            LLMProviderTestOut(
                provider=name, configured=True, ok=ok, latency_ms=latency_ms, error=error
            )
        )

    return results
