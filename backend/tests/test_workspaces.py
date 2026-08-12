from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers, signup


async def _my_workspace_id(client: AsyncClient, access_token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(access_token))
    workspace_id: str = response.json()["memberships"][0]["workspace_id"]
    return workspace_id


async def _invite_and_join(
    client: AsyncClient, *, owner_token: str, workspace_id: str, joiner_token: str
) -> None:
    invite = await client.post(
        f"/api/v1/workspaces/{workspace_id}/members/invite-code",
        headers=auth_headers(owner_token),
    )
    code = invite.json()["code"]
    join = await client.post(
        "/api/v1/workspaces/join", json={"code": code}, headers=auth_headers(joiner_token)
    )
    assert join.status_code == 200, join.text


async def test_create_and_list_workspaces(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]

    create_response = await client.post(
        "/api/v1/workspaces", json={"name": "Team Rocket"}, headers=auth_headers(token)
    )
    assert create_response.status_code == 201
    assert create_response.json()["role"] == "owner"

    list_response = await client.get("/api/v1/workspaces", headers=auth_headers(token))
    assert list_response.status_code == 200
    # personal workspace from signup + the one just created
    assert len(list_response.json()) == 2


async def test_non_member_gets_404_not_403(client: AsyncClient) -> None:
    owner = await signup(client)
    outsider = await signup(client)
    workspace_id = await _my_workspace_id(client, owner["access_token"])

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}", headers=auth_headers(outsider["access_token"])
    )

    assert response.status_code == 404


async def test_responder_gets_403_on_owner_only_endpoints(client: AsyncClient) -> None:
    owner = await signup(client)
    responder = await signup(client)
    workspace_id = await _my_workspace_id(client, owner["access_token"])
    await _invite_and_join(
        client,
        owner_token=owner["access_token"],
        workspace_id=workspace_id,
        joiner_token=responder["access_token"],
    )

    patch_response = await client.patch(
        f"/api/v1/workspaces/{workspace_id}",
        json={"name": "Hijacked"},
        headers=auth_headers(responder["access_token"]),
    )
    invite_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/members/invite-code",
        headers=auth_headers(responder["access_token"]),
    )
    delete_response = await client.delete(
        f"/api/v1/workspaces/{workspace_id}", headers=auth_headers(responder["access_token"])
    )

    assert patch_response.status_code == 403
    assert invite_response.status_code == 403
    assert delete_response.status_code == 403


async def test_owner_can_update_workspace(client: AsyncClient) -> None:
    owner = await signup(client)
    workspace_id = await _my_workspace_id(client, owner["access_token"])

    response = await client.patch(
        f"/api/v1/workspaces/{workspace_id}",
        json={"name": "Renamed Workspace"},
        headers=auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Workspace"


async def test_join_with_invalid_code_is_404(client: AsyncClient) -> None:
    user = await signup(client)

    response = await client.post(
        "/api/v1/workspaces/join",
        json={"code": "not-a-real-code"},
        headers=auth_headers(user["access_token"]),
    )

    assert response.status_code == 404


async def test_join_twice_conflicts(client: AsyncClient) -> None:
    owner = await signup(client)
    joiner = await signup(client)
    workspace_id = await _my_workspace_id(client, owner["access_token"])

    invite = await client.post(
        f"/api/v1/workspaces/{workspace_id}/members/invite-code",
        headers=auth_headers(owner["access_token"]),
    )
    code = invite.json()["code"]

    first_join = await client.post(
        "/api/v1/workspaces/join",
        json={"code": code},
        headers=auth_headers(joiner["access_token"]),
    )
    second_join = await client.post(
        "/api/v1/workspaces/join",
        json={"code": code},
        headers=auth_headers(joiner["access_token"]),
    )

    assert first_join.status_code == 200
    assert second_join.status_code == 409


async def test_owner_can_change_member_role_and_remove_member(client: AsyncClient) -> None:
    owner = await signup(client)
    member = await signup(client)
    workspace_id = await _my_workspace_id(client, owner["access_token"])
    await _invite_and_join(
        client,
        owner_token=owner["access_token"],
        workspace_id=workspace_id,
        joiner_token=member["access_token"],
    )
    member_id: str = (
        await client.get("/api/v1/auth/me", headers=auth_headers(member["access_token"]))
    ).json()["user"]["id"]

    role_response = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{member_id}",
        json={"role": "viewer"},
        headers=auth_headers(owner["access_token"]),
    )
    assert role_response.status_code == 200
    assert role_response.json()["role"] == "viewer"

    remove_response = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/members/{member_id}",
        headers=auth_headers(owner["access_token"]),
    )
    assert remove_response.status_code == 204

    members_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/members", headers=auth_headers(owner["access_token"])
    )
    member_ids = [m["user_id"] for m in members_response.json()]
    assert member_id not in member_ids


async def test_last_owner_cannot_be_demoted_or_removed(client: AsyncClient) -> None:
    owner = await signup(client)
    workspace_id = await _my_workspace_id(client, owner["access_token"])
    owner_id: str = (
        await client.get("/api/v1/auth/me", headers=auth_headers(owner["access_token"]))
    ).json()["user"]["id"]

    demote_response = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{owner_id}",
        json={"role": "responder"},
        headers=auth_headers(owner["access_token"]),
    )
    remove_response = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/members/{owner_id}",
        headers=auth_headers(owner["access_token"]),
    )

    assert demote_response.status_code == 409
    assert remove_response.status_code == 409


async def test_every_mutation_writes_an_audit_log_row(client: AsyncClient) -> None:
    owner = await signup(client)
    workspace_id = await _my_workspace_id(client, owner["access_token"])

    await client.post(
        f"/api/v1/workspaces/{workspace_id}/members/invite-code",
        headers=auth_headers(owner["access_token"]),
    )

    audit_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/audit-log", headers=auth_headers(owner["access_token"])
    )

    assert audit_response.status_code == 200
    actions = [entry["action"] for entry in audit_response.json()["items"]]
    assert "workspace.created" in actions
    assert "workspace.invite_code_rotated" in actions


async def test_audit_log_is_paginated(client: AsyncClient) -> None:
    owner = await signup(client)
    workspace_id = await _my_workspace_id(client, owner["access_token"])

    for _ in range(3):
        await client.post(
            f"/api/v1/workspaces/{workspace_id}/members/invite-code",
            headers=auth_headers(owner["access_token"]),
        )

    first_page = await client.get(
        f"/api/v1/workspaces/{workspace_id}/audit-log?limit=2",
        headers=auth_headers(owner["access_token"]),
    )
    body: dict[str, Any] = first_page.json()

    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None

    second_page = await client.get(
        f"/api/v1/workspaces/{workspace_id}/audit-log?limit=2&cursor={body['next_cursor']}",
        headers=auth_headers(owner["access_token"]),
    )
    assert second_page.status_code == 200
    first_ids = {item["id"] for item in body["items"]}
    second_ids = {item["id"] for item in second_page.json()["items"]}
    assert first_ids.isdisjoint(second_ids)
