import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import WorkspaceMember, WorkspaceRole
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return str(response.json()["memberships"][0]["workspace_id"])


async def _demote_to_viewer(
    client: AsyncClient, db: AsyncSession, workspace_id: str, token: str
) -> None:
    me = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    user_id = me.json()["user"]["id"]
    member = await db.get(WorkspaceMember, (uuid.UUID(workspace_id), uuid.UUID(user_id)))
    assert member is not None
    member.role = WorkspaceRole.VIEWER
    await db.commit()


async def test_owner_can_create_list_and_revoke_a_key(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    create_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/apikeys",
        json={"name": "ci-bot"},
        headers=auth_headers(token),
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["raw_key"].startswith("hs_")
    key_id = created["id"]

    list_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/apikeys", headers=auth_headers(token)
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    # The raw key is never returned again -- not present in the list shape at all.
    assert "raw_key" not in listed[0]
    assert listed[0]["prefix"] == created["prefix"]
    assert listed[0]["revoked_at"] is None

    revoke_response = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/apikeys/{key_id}", headers=auth_headers(token)
    )
    assert revoke_response.status_code == 204

    listed_again = await client.get(
        f"/api/v1/workspaces/{workspace_id}/apikeys", headers=auth_headers(token)
    )
    assert listed_again.json()[0]["revoked_at"] is not None


async def test_revoking_an_already_revoked_key_conflicts(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    created = (
        await client.post(
            f"/api/v1/workspaces/{workspace_id}/apikeys",
            json={"name": "ci-bot"},
            headers=auth_headers(token),
        )
    ).json()

    first = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/apikeys/{created['id']}", headers=auth_headers(token)
    )
    second = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/apikeys/{created['id']}", headers=auth_headers(token)
    )
    assert first.status_code == 204
    assert second.status_code == 409


async def test_viewer_cannot_create_or_list_or_revoke_keys(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    owner_token = owner["access_token"]
    workspace_id = await _workspace_id(client, owner_token)
    created = (
        await client.post(
            f"/api/v1/workspaces/{workspace_id}/apikeys",
            json={"name": "ci-bot"},
            headers=auth_headers(owner_token),
        )
    ).json()
    await _demote_to_viewer(client, db, workspace_id, owner_token)

    create_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/apikeys",
        json={"name": "another"},
        headers=auth_headers(owner_token),
    )
    list_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/apikeys", headers=auth_headers(owner_token)
    )
    revoke_response = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/apikeys/{created['id']}",
        headers=auth_headers(owner_token),
    )

    assert create_response.status_code == 403
    assert list_response.status_code == 403
    assert revoke_response.status_code == 403


async def test_responder_cannot_see_api_keys_either(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    owner_token = owner["access_token"]
    workspace_id = await _workspace_id(client, owner_token)
    me = await client.get("/api/v1/auth/me", headers=auth_headers(owner_token))
    user_id = me.json()["user"]["id"]
    member = await db.get(WorkspaceMember, (uuid.UUID(workspace_id), uuid.UUID(user_id)))
    assert member is not None
    member.role = WorkspaceRole.RESPONDER
    await db.commit()

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/apikeys", headers=auth_headers(owner_token)
    )
    assert response.status_code == 403
