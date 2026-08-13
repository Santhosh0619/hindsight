import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.models.job import Job, JobStatus
from app.workers import queue
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return uuid.UUID(response.json()["memberships"][0]["workspace_id"])


def _unique_kind() -> str:
    # A fresh kind per test -- since claim() filters by kind, this makes each test
    # immune to leftover job rows from other tests or prior runs against the same
    # (non-truncated) dev database, without weakening what's actually being asserted.
    return f"test-kind-{uuid.uuid4().hex[:12]}"


async def test_claim_returns_enqueued_job_and_sets_running(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])
    kind = _unique_kind()
    job = await queue.enqueue(db, workspace_id=workspace_id, kind=kind, payload={"x": 1})

    claimed = await queue.claim(db, worker_id="w1", kinds=[kind], limit=5)

    assert [j.id for j in claimed] == [job.id]
    assert claimed[0].status == JobStatus.RUNNING
    assert claimed[0].locked_by == "w1"


async def test_claim_respects_kind_filter(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])
    kind = _unique_kind()
    await queue.enqueue(db, workspace_id=workspace_id, kind=f"{kind}-other", payload={})

    claimed = await queue.claim(db, worker_id="w1", kinds=[kind], limit=5)

    assert claimed == []


async def test_claim_respects_run_after(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])
    kind = _unique_kind()
    future = datetime.now(UTC) + timedelta(hours=1)
    await queue.enqueue(db, workspace_id=workspace_id, kind=kind, payload={}, run_after=future)

    claimed = await queue.claim(db, worker_id="w1", kinds=[kind], limit=5)

    assert claimed == []


async def test_complete_marks_job_done(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])
    kind = _unique_kind()
    job = await queue.enqueue(db, workspace_id=workspace_id, kind=kind, payload={})
    [claimed] = await queue.claim(db, worker_id="w1", kinds=[kind], limit=5)

    await queue.complete(db, job=claimed)

    refreshed = await db.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.DONE


async def test_fail_retries_with_backoff_then_dead_letters(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])
    kind = _unique_kind()
    job = await queue.enqueue(db, workspace_id=workspace_id, kind=kind, payload={})
    job.max_attempts = 2
    await db.commit()

    [claimed] = await queue.claim(db, worker_id="w1", kinds=[kind], limit=5)
    await queue.fail(db, job=claimed, error="boom")

    refreshed = await db.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.QUEUED
    assert refreshed.attempts == 1
    assert refreshed.run_after > datetime.now(UTC)
    assert refreshed.locked_by is None

    await queue.fail(db, job=refreshed, error="boom again")

    dead = await db.get(Job, job.id)
    assert dead is not None
    assert dead.status == JobStatus.DEAD
    assert dead.attempts == 2
    assert dead.last_error == "boom again"


async def test_reclaim_expired_requeues_stale_running_job(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])
    kind = _unique_kind()
    job = await queue.enqueue(db, workspace_id=workspace_id, kind=kind, payload={})
    [claimed] = await queue.claim(db, worker_id="w1", kinds=[kind], limit=5)
    claimed.locked_at = datetime.now(UTC) - timedelta(seconds=999)
    await db.commit()

    reclaimed_count = await queue.reclaim_expired(db, lease_seconds=120)

    # reclaim_expired is deliberately global, not workspace- or kind-scoped (a worker
    # pool reclaims stale leases across every tenant and job kind) -- assert this job
    # was among those reclaimed rather than asserting an exact count, which a shared
    # jobs table doesn't guarantee in isolation from whatever else is stale at the time.
    assert reclaimed_count >= 1
    refreshed = await db.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.QUEUED
    assert refreshed.attempts == 1


async def test_reclaim_expired_ignores_fresh_running_job(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])
    kind = _unique_kind()
    job = await queue.enqueue(db, workspace_id=workspace_id, kind=kind, payload={})
    await queue.claim(db, worker_id="w1", kinds=[kind], limit=5)

    await queue.reclaim_expired(db, lease_seconds=120)

    # Only asserting this specific job's own state -- see the sibling test above for
    # why reclaim_expired's aggregate count isn't asserted directly.
    refreshed = await db.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.RUNNING


async def test_concurrent_claims_never_overlap(client: AsyncClient) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])
    kind = _unique_kind()

    session_factory = get_session_factory()
    async with session_factory() as setup_db:
        for _ in range(10):
            await queue.enqueue(setup_db, workspace_id=workspace_id, kind=kind, payload={})

    async def claim_batch() -> list[uuid.UUID]:
        async with session_factory() as claim_db:
            jobs = await queue.claim(
                claim_db, worker_id=f"w-{uuid.uuid4().hex[:6]}", kinds=[kind], limit=5
            )
            return [j.id for j in jobs]

    ids_a, ids_b = await asyncio.gather(claim_batch(), claim_batch())

    assert set(ids_a).isdisjoint(set(ids_b))
    assert len(ids_a) + len(ids_b) == 10
