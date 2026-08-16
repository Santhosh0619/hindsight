from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.settings import ModelSettings

from app.services.llm.provider import LLMResponse, T


class GeminiProvider:
    def __init__(self, *, api_key: str, model: str, request_timeout_seconds: int = 30) -> None:
        self.model_name = model
        self._api_key = api_key
        self._model: GoogleModel | None = None
        # Phase 14 hardening -- see docs/modules/phase-14-hardening/FRD.md "Outbound
        # LLM call timeouts". An explicit, documented value rather than relying on
        # whatever pydantic-ai/httpx default happens to apply.
        self._model_settings: ModelSettings = {"timeout": request_timeout_seconds}

    def _get_model(self) -> GoogleModel:
        # Built on first use, not at __init__ -- constructing the underlying client
        # eagerly would do real work (and could fail) before the provider is ever
        # actually called.
        if self._model is None:
            self._model = GoogleModel(
                self.model_name, provider=GoogleProvider(api_key=self._api_key)
            )
        return self._model

    async def complete(self, prompt: str, *, system: str) -> LLMResponse:
        agent = Agent(self._get_model(), system_prompt=system)
        result = await agent.run(prompt, model_settings=self._model_settings)
        return LLMResponse(
            text=result.output,
            tokens_in=result.usage.input_tokens,
            tokens_out=result.usage.output_tokens,
            model=self.model_name,
        )

    async def structured(self, prompt: str, *, system: str, result_type: type[T]) -> T:
        agent = Agent(self._get_model(), output_type=result_type, system_prompt=system)
        result = await agent.run(prompt, model_settings=self._model_settings)
        return result.output

    async def structured_with_usage(
        self, prompt: str, *, system: str, result_type: type[T]
    ) -> tuple[T, LLMResponse]:
        agent = Agent(self._get_model(), output_type=result_type, system_prompt=system)
        result = await agent.run(prompt, model_settings=self._model_settings)
        usage = LLMResponse(
            text="",
            tokens_in=result.usage.input_tokens,
            tokens_out=result.usage.output_tokens,
            model=self.model_name,
        )
        return result.output, usage
