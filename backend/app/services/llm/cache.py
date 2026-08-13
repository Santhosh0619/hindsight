import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import SemanticCache
from app.services.ingestion.embed import embed

_DEFAULT_THRESHOLD = 0.05


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


async def get_cached(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    purpose: str,
    prompt: str,
    threshold: float = _DEFAULT_THRESHOLD,
) -> dict[str, object] | None:
    prompt_hash = _hash_prompt(prompt)

    # Cheap path: an exact-text repeat never needs an embedding call at all.
    exact_result = await db.execute(
        select(SemanticCache).where(
            SemanticCache.workspace_id == workspace_id,
            SemanticCache.purpose == purpose,
            SemanticCache.prompt_hash == prompt_hash,
        )
    )
    exact_hit = exact_result.scalars().first()
    if exact_hit is not None:
        exact_hit.hits += 1
        await db.commit()
        return exact_hit.response

    [embedding] = await embed([prompt])
    distance_col = SemanticCache.embedding.cosine_distance(embedding)
    semantic_result = await db.execute(
        select(SemanticCache, distance_col.label("distance"))
        .where(
            SemanticCache.workspace_id == workspace_id,
            SemanticCache.purpose == purpose,
            SemanticCache.embedding.is_not(None),
        )
        .order_by(distance_col)
        .limit(1)
    )
    row = semantic_result.first()
    if row is None:
        return None
    entry: SemanticCache = row[0]
    distance: float = row[1]
    if distance > threshold:
        return None
    entry.hits += 1
    await db.commit()
    response: dict[str, object] = entry.response
    return response


async def store(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    purpose: str,
    prompt: str,
    model: str,
    response: dict[str, object],
) -> None:
    [embedding] = await embed([prompt])
    db.add(
        SemanticCache(
            workspace_id=workspace_id,
            purpose=purpose,
            prompt_hash=_hash_prompt(prompt),
            embedding=embedding,
            response=response,
            model=model,
        )
    )
    await db.commit()
