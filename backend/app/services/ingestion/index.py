from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postmortem import Postmortem, PostmortemChunk, PostmortemStatus
from app.services.ingestion.chunk import ChunkSpan


async def index_postmortem(
    db: AsyncSession,
    *,
    postmortem: Postmortem,
    chunks: list[ChunkSpan],
    embeddings: list[list[float]],
) -> None:
    # Re-ingestion safety: drop any chunks from a prior attempt before writing the new
    # set, so a re-run never leaves stale chunks alongside fresh ones.
    await db.execute(delete(PostmortemChunk).where(PostmortemChunk.postmortem_id == postmortem.id))

    for chunk_index, (span, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
        db.add(
            PostmortemChunk(
                postmortem_id=postmortem.id,
                chunk_index=chunk_index,
                section_label=span.section_label,
                content=span.content,
                char_start=span.char_start,
                char_end=span.char_end,
                embedding=embedding,
                tsv=func.to_tsvector("english", span.content),
            )
        )
    postmortem.status = PostmortemStatus.INDEXED
    await db.commit()
