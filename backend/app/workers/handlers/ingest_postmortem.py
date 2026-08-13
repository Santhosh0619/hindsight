import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.job import Job
from app.models.postmortem import Postmortem, PostmortemStatus
from app.services.ingestion.chunk import chunk
from app.services.ingestion.embed import embed
from app.services.ingestion.index import index_postmortem
from app.services.ingestion.redact import redact
from app.services.ingestion.screen import screen
from app.workers import queue

logger = get_logger(__name__)


async def handle_ingest_postmortem(db: AsyncSession, job: Job) -> None:
    postmortem_id = uuid.UUID(str(job.payload["postmortem_id"]))
    postmortem = await db.get(Postmortem, postmortem_id)
    if postmortem is None:
        # Deleted before the job ran -- nothing to ingest, not a failure.
        return

    postmortem.status = PostmortemStatus.PROCESSING
    await db.commit()

    start = time.monotonic()
    try:
        redacted = redact(postmortem.raw_text)
        injection_flagged = screen(redacted)
        spans = chunk(redacted)
        embeddings = await embed([span.content for span in spans])

        postmortem.redacted_text = redacted
        postmortem.injection_flagged = injection_flagged
        await index_postmortem(db, postmortem=postmortem, chunks=spans, embeddings=embeddings)
        await queue.enqueue(
            db,
            workspace_id=postmortem.workspace_id,
            kind="extract_postmortem",
            payload={"postmortem_id": str(postmortem_id)},
        )
        logger.info(
            "postmortem_ingested",
            postmortem_id=str(postmortem_id),
            chunk_count=len(spans),
            injection_flagged=injection_flagged,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as exc:
        await db.rollback()
        postmortem = await db.get(Postmortem, postmortem_id)
        if postmortem is not None:
            postmortem.status = PostmortemStatus.FAILED
            postmortem.failure_reason = str(exc)[:2000]
            await db.commit()
        raise
