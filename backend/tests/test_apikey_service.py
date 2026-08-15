import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, UnauthorizedError
from app.services import apikey_service
from tests.conftest import auth_headers, signup


async def _workspace_and_user(client: AsyncClient, token: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    body = response.json()
    return uuid.UUID(body["memberships"][0]["workspace_id"]), uuid.UUID(body["user"]["id"])


async def test_create_key_returns_a_raw_key_with_a_matching_prefix(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id, user_id = await _workspace_and_user(client, owner["access_token"])

    key, raw_key = await apikey_service.create_key(
        db, workspace_id=workspace_id, name="ci-bot", actor_user_id=user_id
    )

    assert raw_key.startswith("hs_")
    assert raw_key.startswith(key.prefix)
    # The hash stored is never the raw key itself, nor does it embed enough to recover
    # the key -- just proving they're not literally equal is the cheap, real check.
    assert key.key_hash != raw_key


async def test_authenticate_key_resolves_the_owning_workspace(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id, user_id = await _workspace_and_user(client, owner["access_token"])
    _key, raw_key = await apikey_service.create_key(
        db, workspace_id=workspace_id, name="ci-bot", actor_user_id=user_id
    )

    resolved = await apikey_service.authenticate_key(db, raw_key=raw_key)
    assert resolved.workspace_id == workspace_id
    assert resolved.created_by == user_id


async def test_authenticate_key_rejects_an_unknown_key(
    client: AsyncClient, db: AsyncSession
) -> None:
    with pytest.raises(UnauthorizedError):
        await apikey_service.authenticate_key(db, raw_key="hs_totally-made-up")


async def test_authenticate_key_rejects_a_revoked_key(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id, user_id = await _workspace_and_user(client, owner["access_token"])
    key, raw_key = await apikey_service.create_key(
        db, workspace_id=workspace_id, name="ci-bot", actor_user_id=user_id
    )
    await apikey_service.revoke_key(
        db, workspace_id=workspace_id, key_id=key.id, actor_user_id=user_id
    )

    with pytest.raises(UnauthorizedError):
        await apikey_service.authenticate_key(db, raw_key=raw_key)


async def test_revoking_an_already_revoked_key_conflicts(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id, user_id = await _workspace_and_user(client, owner["access_token"])
    key, _raw_key = await apikey_service.create_key(
        db, workspace_id=workspace_id, name="ci-bot", actor_user_id=user_id
    )
    await apikey_service.revoke_key(
        db, workspace_id=workspace_id, key_id=key.id, actor_user_id=user_id
    )

    with pytest.raises(ConflictError):
        await apikey_service.revoke_key(
            db, workspace_id=workspace_id, key_id=key.id, actor_user_id=user_id
        )


async def test_revoking_a_key_from_the_wrong_workspace_404s(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner_a = await signup(client)
    owner_b = await signup(client)
    workspace_a, user_a = await _workspace_and_user(client, owner_a["access_token"])
    workspace_b, _user_b = await _workspace_and_user(client, owner_b["access_token"])
    key, _raw_key = await apikey_service.create_key(
        db, workspace_id=workspace_a, name="ci-bot", actor_user_id=user_a
    )

    with pytest.raises(NotFoundError):
        await apikey_service.revoke_key(
            db, workspace_id=workspace_b, key_id=key.id, actor_user_id=user_a
        )
