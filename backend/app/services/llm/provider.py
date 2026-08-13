from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMResponse(BaseModel):
    text: str
    tokens_in: int
    tokens_out: int
    model: str


class LLMProvider(Protocol):
    model_name: str

    async def complete(self, prompt: str, *, system: str) -> LLMResponse: ...

    async def structured(self, prompt: str, *, system: str, result_type: type[T]) -> T: ...
