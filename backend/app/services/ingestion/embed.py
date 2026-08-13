import asyncio
from typing import cast

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

# Loaded once per worker process (not once per job) -- a cold model load takes seconds,
# and this module is only ever imported by the worker, never by a request handler.
_model: SentenceTransformer | None = None
_model_lock = asyncio.Lock()


async def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        async with _model_lock:
            if _model is None:
                settings = get_settings()
                _model = await asyncio.to_thread(SentenceTransformer, settings.embedding_model)
    model = _model
    assert model is not None
    return model


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = await _get_model()
    # model.encode is CPU-bound and synchronous -- run off the event loop thread so it
    # doesn't block other jobs' I/O while a batch encodes.
    embeddings = await asyncio.to_thread(model.encode, texts, batch_size=32)
    return cast(list[list[float]], embeddings.tolist())
