import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.job import Job
from app.services.extraction_service import run_extraction
from app.services.llm.router import build_router

logger = get_logger(__name__)


async def handle_extract_postmortem(db: AsyncSession, job: Job) -> None:
    postmortem_id = uuid.UUID(str(job.payload["postmortem_id"]))
    router = build_router(get_settings())

    start = time.monotonic()
    summary = await run_extraction(db, router, postmortem_id=postmortem_id)
    logger.info(
        "postmortem_extracted",
        postmortem_id=str(postmortem_id),
        fact_count=summary.fact_count,
        failure_mode_count=summary.failure_mode_count,
        service_link_count=summary.service_link_count,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
