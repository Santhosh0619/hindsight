import asyncio
import signal
import time
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, get_session_factory
from app.models.job import Job, JobStatus
from app.workers import queue
from app.workers.handlers.ingest_postmortem import handle_ingest_postmortem

logger = get_logger(__name__)

POLL_INTERVAL_SECONDS = 2.0
CLAIM_BATCH_SIZE = 5
MAX_CONCURRENT_JOBS = 5

JobHandler = Callable[[AsyncSession, Job], Awaitable[None]]

_HANDLERS: dict[str, JobHandler] = {"ingest_postmortem": handle_ingest_postmortem}


class Worker:
    def __init__(
        self, handlers: dict[str, JobHandler] | None = None, worker_id: str | None = None
    ) -> None:
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._handlers = handlers if handlers is not None else _HANDLERS
        self._shutdown_requested = False
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        self._in_flight: set[asyncio.Task[None]] = set()

    def request_shutdown(self) -> None:
        self._shutdown_requested = True

    async def run(self) -> None:
        logger.info("worker_started", worker_id=self.worker_id)
        session_factory = get_session_factory()
        while not self._shutdown_requested:
            async with session_factory() as db:
                reclaimed = await queue.reclaim_expired(
                    db, lease_seconds=get_settings().job_lease_seconds
                )
            if reclaimed:
                logger.warning("jobs_reclaimed", worker_id=self.worker_id, count=reclaimed)

            async with session_factory() as db:
                jobs = await queue.claim(
                    db,
                    worker_id=self.worker_id,
                    kinds=list(self._handlers),
                    limit=CLAIM_BATCH_SIZE,
                )

            if not jobs:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            for job in jobs:
                task = asyncio.create_task(self._run_job(job.id, job.kind))
                self._in_flight.add(task)
                task.add_done_callback(self._in_flight.discard)

        logger.info(
            "worker_shutting_down", worker_id=self.worker_id, in_flight=len(self._in_flight)
        )
        if self._in_flight:
            await asyncio.wait(self._in_flight)
        logger.info("worker_stopped", worker_id=self.worker_id)

    async def _run_job(self, job_id: uuid.UUID, kind: str) -> None:
        async with self._semaphore:
            session_factory = get_session_factory()
            handler = self._handlers[kind]
            start = time.monotonic()
            async with session_factory() as db:
                job = await db.get(Job, job_id)
                if job is None:
                    return
                try:
                    await handler(db, job)
                    await queue.complete(db, job=job)
                    logger.info(
                        "job_completed",
                        job_id=str(job_id),
                        kind=kind,
                        workspace_id=str(job.workspace_id),
                        latency_ms=int((time.monotonic() - start) * 1000),
                    )
                except Exception as exc:  # noqa: BLE001 -- a handler's failure must never
                    # crash the worker process; it's recorded and retried/dead-lettered.
                    await db.rollback()
                    job = await db.get(Job, job_id)
                    if job is None:
                        return
                    await queue.fail(db, job=job, error=str(exc)[:2000])
                    event = "job_dead_lettered" if job.status == JobStatus.DEAD else "job_failed"
                    logger.warning(
                        event,
                        job_id=str(job_id),
                        kind=kind,
                        workspace_id=str(job.workspace_id),
                        error=str(exc),
                        attempts=job.attempts,
                    )


async def _main() -> None:
    configure_logging()
    worker = Worker()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.request_shutdown)

    try:
        await worker.run()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
