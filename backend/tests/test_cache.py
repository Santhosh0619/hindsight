import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import SemanticCache
from app.services.llm.cache import get_cached, store
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return uuid.UUID(response.json()["memberships"][0]["workspace_id"])


async def test_exact_hash_hit_returns_the_stored_response(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])

    await store(
        db,
        workspace_id=workspace_id,
        purpose="extract_facts",
        prompt="What caused the checkout outage?",
        model="test-model",
        response={"answer": "a bad deploy"},
    )

    hit = await get_cached(
        db,
        workspace_id=workspace_id,
        purpose="extract_facts",
        prompt="What caused the checkout outage?",
    )

    assert hit == {"answer": "a bad deploy"}


async def test_miss_returns_none_and_does_not_error(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])

    hit = await get_cached(
        db, workspace_id=workspace_id, purpose="extract_facts", prompt="Nothing cached for this."
    )

    assert hit is None


async def test_hit_increments_hits(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])

    await store(
        db,
        workspace_id=workspace_id,
        purpose="extract_facts",
        prompt="repeated prompt",
        model="test-model",
        response={"x": 1},
    )
    await get_cached(
        db, workspace_id=workspace_id, purpose="extract_facts", prompt="repeated prompt"
    )
    await get_cached(
        db, workspace_id=workspace_id, purpose="extract_facts", prompt="repeated prompt"
    )

    result = await db.execute(
        select(SemanticCache).where(SemanticCache.workspace_id == workspace_id)
    )
    entry = result.scalars().one()
    assert entry.hits == 2


async def test_cache_is_scoped_by_purpose(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])

    await store(
        db,
        workspace_id=workspace_id,
        purpose="extract_facts",
        prompt="same prompt text",
        model="test-model",
        response={"scope": "facts"},
    )

    hit = await get_cached(
        db, workspace_id=workspace_id, purpose="generate_brief", prompt="same prompt text"
    )

    assert hit is None


async def test_cache_is_scoped_by_workspace(client: AsyncClient, db: AsyncSession) -> None:
    owner_a = await signup(client)
    owner_b = await signup(client)
    workspace_a = await _workspace_id(client, owner_a["access_token"])
    workspace_b = await _workspace_id(client, owner_b["access_token"])

    await store(
        db,
        workspace_id=workspace_a,
        purpose="extract_facts",
        prompt="cross-tenant prompt",
        model="test-model",
        response={"scope": "a"},
    )

    hit = await get_cached(
        db, workspace_id=workspace_b, purpose="extract_facts", prompt="cross-tenant prompt"
    )

    assert hit is None
