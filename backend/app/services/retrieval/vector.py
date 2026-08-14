import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postmortem import Postmortem, PostmortemChunk

# Cosine distance is 0 (identical) to 2 (opposite); a query with nothing meaningfully
# close in the corpus should return fewer than top_k results, not top_k worth of noise.
DEFAULT_MAX_DISTANCE = 0.7


class VectorHit(BaseModel):
    chunk_id: uuid.UUID
    postmortem_id: uuid.UUID
    distance: float
    rank: int


async def search_vector(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    max_distance: float = DEFAULT_MAX_DISTANCE,
) -> list[VectorHit]:
    distance_col = PostmortemChunk.embedding.cosine_distance(query_embedding)
    query = (
        select(PostmortemChunk.id, PostmortemChunk.postmortem_id, distance_col.label("distance"))
        .join(Postmortem, Postmortem.id == PostmortemChunk.postmortem_id)
        .where(
            Postmortem.workspace_id == workspace_id,
            PostmortemChunk.embedding.is_not(None),
            distance_col <= max_distance,
        )
        .order_by(distance_col)
        .limit(top_k)
    )
    result = await db.execute(query)
    return [
        VectorHit(
            chunk_id=row.id, postmortem_id=row.postmortem_id, distance=row.distance, rank=i + 1
        )
        for i, row in enumerate(result)
    ]
