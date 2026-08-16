from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from app.services.llm.provider import LLMResponse, T


class OllamaLLMProvider:
    def __init__(self, *, base_url: str, model: str, request_timeout_seconds: int = 30) -> None:
        self.model_name = model
        self._base_url = base_url
        self._model: OllamaModel | None = None
        self._model_settings: ModelSettings = {"timeout": request_timeout_seconds}

    def _get_model(self) -> OllamaModel:
        if self._model is None:
            self._model = OllamaModel(
                self.model_name, provider=OllamaProvider(base_url=self._base_url)
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
