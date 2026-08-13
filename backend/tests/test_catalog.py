from httpx import AsyncClient

from tests.conftest import auth_headers, signup


async def _my_workspace_id(client: AsyncClient, access_token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(access_token))
    workspace_id: str = response.json()["memberships"][0]["workspace_id"]
    return workspace_id


async def _invite_and_join(
    client: AsyncClient, *, owner_token: str, workspace_id: str, joiner_token: str, role: str
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
    if role != "responder":
        member_id: str = (
            await client.get("/api/v1/auth/me", headers=auth_headers(joiner_token))
        ).json()["user"]["id"]
        role_response = await client.patch(
            f"/api/v1/workspaces/{workspace_id}/members/{member_id}",
            json={"role": role},
            headers=auth_headers(owner_token),
        )
        assert role_response.status_code == 200, role_response.text


async def _create_service(
    client: AsyncClient, *, token: str, workspace_id: str, name: str, tier: int = 1
) -> str:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": name, "tier": tier},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    service_id: str = response.json()["id"]
    return service_id


async def test_team_crud(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    create_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/teams",
        json={"name": "Payments", "slack_handle": "#payments"},
        headers=auth_headers(token),
    )
    assert create_response.status_code == 201, create_response.text
    team_id = create_response.json()["id"]

    list_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/teams", headers=auth_headers(token)
    )
    assert len(list_response.json()) == 1

    patch_response = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/catalog/teams/{team_id}",
        json={"name": "Payments Platform"},
        headers=auth_headers(token),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Payments Platform"

    delete_response = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/catalog/teams/{team_id}", headers=auth_headers(token)
    )
    assert delete_response.status_code == 204

    empty_list = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/teams", headers=auth_headers(token)
    )
    assert empty_list.json() == []


async def test_service_crud_and_duplicate_name_conflicts(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    service_id = await _create_service(client, token=token, workspace_id=workspace_id, name="api")

    duplicate_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": "api", "tier": 2},
        headers=auth_headers(token),
    )
    assert duplicate_response.status_code == 409

    get_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/services/{service_id}",
        headers=auth_headers(token),
    )
    assert get_response.status_code == 200
    assert get_response.json()["tier"] == 1

    patch_response = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/catalog/services/{service_id}",
        json={"tier": 2, "description": "Public API gateway"},
        headers=auth_headers(token),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["tier"] == 2

    delete_response = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/catalog/services/{service_id}",
        headers=auth_headers(token),
    )
    assert delete_response.status_code == 204

    missing_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/services/{service_id}",
        headers=auth_headers(token),
    )
    assert missing_response.status_code == 404


async def test_service_list_filters_by_team_and_tier(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    team_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/teams",
        json={"name": "Platform"},
        headers=auth_headers(token),
    )
    team_id = team_response.json()["id"]

    await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": "with-team", "tier": 1, "team_id": team_id},
        headers=auth_headers(token),
    )
    await _create_service(client, token=token, workspace_id=workspace_id, name="no-team", tier=3)

    filtered = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/services?team_id={team_id}",
        headers=auth_headers(token),
    )
    assert [s["name"] for s in filtered.json()] == ["with-team"]


async def test_edge_self_edge_rejected(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)
    service_id = await _create_service(client, token=token, workspace_id=workspace_id, name="api")

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/edges",
        json={
            "from_service_id": service_id,
            "to_service_id": service_id,
            "kind": "calls",
            "criticality": "hard",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 422


async def test_edge_duplicate_conflicts(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)
    a = await _create_service(client, token=token, workspace_id=workspace_id, name="a")
    b = await _create_service(client, token=token, workspace_id=workspace_id, name="b")

    payload = {
        "from_service_id": a,
        "to_service_id": b,
        "kind": "calls",
        "criticality": "hard",
    }
    first = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/edges",
        json=payload,
        headers=auth_headers(token),
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/edges",
        json=payload,
        headers=auth_headers(token),
    )
    assert second.status_code == 409

    edge_id = first.json()["id"]
    delete_response = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/catalog/edges/{edge_id}", headers=auth_headers(token)
    )
    assert delete_response.status_code == 204


async def test_edge_to_cross_workspace_service_is_404(client: AsyncClient) -> None:
    owner = await signup(client)
    other_owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)
    other_workspace_id = await _my_workspace_id(client, other_owner["access_token"])

    a = await _create_service(client, token=token, workspace_id=workspace_id, name="a")
    foreign = await _create_service(
        client, token=other_owner["access_token"], workspace_id=other_workspace_id, name="foreign"
    )

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/edges",
        json={
            "from_service_id": a,
            "to_service_id": foreign,
            "kind": "calls",
            "criticality": "hard",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 404


async def test_viewer_gets_403_on_writes_but_can_read(client: AsyncClient) -> None:
    owner = await signup(client)
    viewer = await signup(client)
    owner_token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, owner_token)
    await _invite_and_join(
        client,
        owner_token=owner_token,
        workspace_id=workspace_id,
        joiner_token=viewer["access_token"],
        role="viewer",
    )

    create_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": "api", "tier": 1},
        headers=auth_headers(viewer["access_token"]),
    )
    assert create_response.status_code == 403

    list_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        headers=auth_headers(viewer["access_token"]),
    )
    assert list_response.status_code == 200


async def test_non_member_gets_404(client: AsyncClient) -> None:
    owner = await signup(client)
    outsider = await signup(client)
    workspace_id = await _my_workspace_id(client, owner["access_token"])

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        headers=auth_headers(outsider["access_token"]),
    )
    assert response.status_code == 404


async def test_import_creates_teams_services_and_edges_by_name(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/import",
        json={
            "teams": [{"name": "Platform"}],
            "services": [
                {"name": "gateway", "tier": 1, "team_name": "Platform"},
                {"name": "database", "tier": 2},
            ],
            "edges": [
                {
                    "from_service_name": "gateway",
                    "to_service_name": "database",
                    "kind": "calls",
                    "criticality": "hard",
                }
            ],
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"teams_created": 1, "services_created": 2, "edges_created": 1}

    graph_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/graph", headers=auth_headers(token)
    )
    assert len(graph_response.json()["nodes"]) == 2
    assert len(graph_response.json()["edges"]) == 1


async def test_import_with_unknown_service_name_rolls_back_entirely(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/import",
        json={
            "teams": [],
            "services": [{"name": "gateway", "tier": 1}],
            "edges": [
                {
                    "from_service_name": "gateway",
                    "to_service_name": "does-not-exist",
                    "kind": "calls",
                    "criticality": "hard",
                }
            ],
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 422

    graph_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/graph", headers=auth_headers(token)
    )
    # nothing partially applied -- not even the service that resolved cleanly
    assert graph_response.json()["nodes"] == []
