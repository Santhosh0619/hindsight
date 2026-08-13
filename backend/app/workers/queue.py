import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus

# Exponential backoff between retries, capped so a chronically-failing job doesn't end
# up waiting hours between attempts before it finally reaches max_attempts.
_MAX_BACKOFF_SECONDS = 300

_CLAIM_SQL = """
UPDATE jobs
SET status = 'running', locked_by = :worker_id, locked_at = now()
WHERE id IN (
    SELECT id FROM jobs
    WHERE status = 'queued' AND run_after <= now() AND kind = ANY(:kinds ::text[])
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :limit
)
RETURNING id
"""


def _backoff_seconds(attempts: int) -> int:
    # int(...) because typeshed's int.__pow__ returns Any (it must accommodate
    # negative exponents returning float), not because this can be non-int at runtime.
    return int(min(2**attempts, _MAX_BACKOFF_SECONDS))


async def enqueue(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    kind: str,
    payload: dict[str, object],
    run_after: datetime | None = None,
) -> Job:
    job = Job(
        workspace_id=workspace_id,
        kind=kind,
        payload=payload,
        run_after=run_after or datetime.now(UTC),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def claim(db: AsyncSession, *, worker_id: str, kinds: list[str], limit: int) -> list[Job]:
    # A single atomic UPDATE ... FOR UPDATE SKIP LOCKED -- two workers calling this
    # concurrently can never claim the same row, with no application-level locking.
    result = await db.execute(
        text(_CLAIM_SQL), {"worker_id": worker_id, "kinds": kinds, "limit": limit}
    )
    await db.commit()
    claimed_ids = [row.id for row in result]
    if not claimed_ids:
        return []
    # populate_existing: if this session already holds one of these Job objects in its
    # identity map (e.g. the same session that enqueued it), the default SELECT
    # behavior returns the cached, now-stale in-memory object instead of picking up
    # the status='running' just written by the UPDATE above.
    jobs_result = await db.execute(
        select(Job).where(Job.id.in_(claimed_ids)).execution_options(populate_existing=True)
    )
    return list(jobs_result.scalars().all())


async def complete(db: AsyncSession, *, job: Job) -> None:
    job.status = JobStatus.DONE
    await db.commit()


async def fail(db: AsyncSession, *, job: Job, error: str) -> None:
    job.attempts += 1
    job.last_error = error
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.DEAD
    else:
        job.status = JobStatus.QUEUED
        job.run_after = datetime.now(UTC) + timedelta(seconds=_backoff_seconds(job.attempts))
        job.locked_by = None
        job.locked_at = None
    await db.commit()


async def reclaim_expired(db: AsyncSession, *, lease_seconds: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=lease_seconds)
    result = await db.execute(
        select(Job).where(Job.status == JobStatus.RUNNING, Job.locked_at < cutoff)
    )
    stale_jobs = list(result.scalars().all())
    for job in stale_jobs:
        # Routed through the same retry/dead-letter path as an explicit failure -- a
        # job that reliably crashes its worker must still eventually reach `dead`,
        # not retry forever just because it crashes the process instead of raising.
        await fail(db, job=job, error="Job reclaimed after lease expiry (worker crashed or killed)")
    return len(stale_jobs)
