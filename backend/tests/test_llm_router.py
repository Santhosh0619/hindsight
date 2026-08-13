import pytest

from app.core.errors import LLMUnavailableError
from app.services.llm.provider import LLMResponse
from app.services.llm.router import LLMRouter


class _FakeProvider:
    def __init__(self, model_name: str, *, fails: bool = False) -> None:
        self.model_name = model_name
        self._fails = fails
        self.calls = 0

    async def complete(self, prompt: str, *, system: str) -> LLMResponse:
        self.calls += 1
        if self._fails:
            raise RuntimeError(f"{self.model_name} is down")
        return LLMResponse(
            text=f"reply from {self.model_name}", tokens_in=1, tokens_out=1, model=self.model_name
        )

    async def structured(self, prompt, *, system, result_type):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self._fails:
            raise RuntimeError(f"{self.model_name} is down")
        return result_type()


async def test_uses_the_first_working_provider() -> None:
    primary = _FakeProvider("primary")
    fallback = _FakeProvider("fallback")
    router = LLMRouter([primary, fallback])

    response = await router.complete("hello", system="sys")

    assert response.model == "primary"
    assert fallback.calls == 0


async def test_falls_back_when_the_primary_provider_fails() -> None:
    primary = _FakeProvider("primary", fails=True)
    fallback = _FakeProvider("fallback")
    router = LLMRouter([primary, fallback])

    response = await router.complete("hello", system="sys")

    assert response.model == "fallback"
    # Retried within the failing provider before moving on, not just tried once.
    assert primary.calls > 1


async def test_raises_llm_unavailable_when_every_provider_fails() -> None:
    router = LLMRouter([_FakeProvider("a", fails=True), _FakeProvider("b", fails=True)])

    with pytest.raises(LLMUnavailableError) as exc_info:
        await router.complete("hello", system="sys")

    assert "a" in str(exc_info.value.detail)
    assert "b" in str(exc_info.value.detail)


async def test_structured_falls_back_too() -> None:
    from pydantic import BaseModel

    class Out(BaseModel):
        pass

    primary = _FakeProvider("primary", fails=True)
    fallback = _FakeProvider("fallback")
    router = LLMRouter([primary, fallback])

    result = await router.structured("hello", system="sys", result_type=Out)

    assert isinstance(result, Out)
