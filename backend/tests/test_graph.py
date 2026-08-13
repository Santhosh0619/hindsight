from httpx import AsyncClient

from tests.conftest import auth_headers, signup


async def _my_workspace_id(client: AsyncClient, access_token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(access_token))
    workspace_id: str = response.json()["memberships"][0]["workspace_id"]
    return workspace_id


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


async def _create_edge(
    client: AsyncClient,
    *,
    token: str,
    workspace_id: str,
    from_id: str,
    to_id: str,
    criticality: str = "hard",
) -> None:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/edges",
        json={
            "from_service_id": from_id,
            "to_service_id": to_id,
            "kind": "calls",
            "criticality": criticality,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text


async def _blast_radius(
    client: AsyncClient, *, token: str, workspace_id: str, service_id: str, depth: int = 4
) -> dict:
    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/catalog/services/{service_id}"
        f"/blast-radius?depth={depth}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    result: dict = response.json()
    return result


async def test_linear_chain_reachability_and_depths(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    a = await _create_service(client, token=token, workspace_id=workspace_id, name="a")
    b = await _create_service(client, token=token, workspace_id=workspace_id, name="b")
    c = await _create_service(client, token=token, workspace_id=workspace_id, name="c")
    d = await _create_service(client, token=token, workspace_id=workspace_id, name="d")
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=a, to_id=b)
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=b, to_id=c)
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=c, to_id=d)

    radius = await _blast_radius(
        client, token=token, workspace_id=workspace_id, service_id=a, depth=10
    )

    depth_by_service = {entry["service"]["id"]: entry["depth"] for entry in radius["services"]}
    assert depth_by_service == {b: 1, c: 2, d: 3}
    assert a not in depth_by_service

    entry_for_c = next(e for e in radius["services"] if e["service"]["id"] == c)
    path_ids = [hop["id"] for hop in entry_for_c["path"]]
    assert path_ids == [a, b, c]
    # path hops are full ServiceOut objects, not bare ids
    assert all("name" in hop and "tier" in hop for hop in entry_for_c["path"])


async def test_depth_cap_limits_reach(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    a = await _create_service(client, token=token, workspace_id=workspace_id, name="a")
    b = await _create_service(client, token=token, workspace_id=workspace_id, name="b")
    c = await _create_service(client, token=token, workspace_id=workspace_id, name="c")
    d = await _create_service(client, token=token, workspace_id=workspace_id, name="d")
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=a, to_id=b)
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=b, to_id=c)
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=c, to_id=d)

    shallow = await _blast_radius(
        client, token=token, workspace_id=workspace_id, service_id=a, depth=1
    )
    deep = await _blast_radius(
        client, token=token, workspace_id=workspace_id, service_id=a, depth=3
    )

    assert {e["service"]["id"] for e in shallow["services"]} == {b}
    assert {e["service"]["id"] for e in deep["services"]} == {b, c, d}


async def test_diamond_dependency_counted_once_via_shortest_path(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    a = await _create_service(client, token=token, workspace_id=workspace_id, name="a")
    b = await _create_service(client, token=token, workspace_id=workspace_id, name="b")
    c = await _create_service(client, token=token, workspace_id=workspace_id, name="c")
    d = await _create_service(client, token=token, workspace_id=workspace_id, name="d")
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=a, to_id=b)
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=a, to_id=c)
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=b, to_id=d)
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=c, to_id=d)

    radius = await _blast_radius(
        client, token=token, workspace_id=workspace_id, service_id=a, depth=10
    )

    entries_for_d = [e for e in radius["services"] if e["service"]["id"] == d]
    assert len(entries_for_d) == 1
    assert entries_for_d[0]["depth"] == 2


async def test_cycle_terminates_and_excludes_the_root(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    a = await _create_service(client, token=token, workspace_id=workspace_id, name="a")
    b = await _create_service(client, token=token, workspace_id=workspace_id, name="b")
    c = await _create_service(client, token=token, workspace_id=workspace_id, name="c")
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=a, to_id=b)
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=b, to_id=c)
    await _create_edge(client, token=token, workspace_id=workspace_id, from_id=c, to_id=a)

    radius = await _blast_radius(
        client, token=token, workspace_id=workspace_id, service_id=a, depth=10
    )

    reached_ids = {e["service"]["id"] for e in radius["services"]}
    assert reached_ids == {b, c}
    assert a not in reached_ids


async def test_hard_edge_scores_higher_than_soft_edge(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    a = await _create_service(client, token=token, workspace_id=workspace_id, name="a")
    hard_target = await _create_service(
        client, token=token, workspace_id=workspace_id, name="hard-target"
    )
    soft_target = await _create_service(
        client, token=token, workspace_id=workspace_id, name="soft-target"
    )
    await _create_edge(
        client,
        token=token,
        workspace_id=workspace_id,
        from_id=a,
        to_id=hard_target,
        criticality="hard",
    )
    await _create_edge(
        client,
        token=token,
        workspace_id=workspace_id,
        from_id=a,
        to_id=soft_target,
        criticality="soft",
    )

    radius = await _blast_radius(
        client, token=token, workspace_id=workspace_id, service_id=a, depth=10
    )

    score_by_service = {e["service"]["id"]: e["score"] for e in radius["services"]}
    assert score_by_service[hard_target] > score_by_service[soft_target]
    # scores come back sorted descending
    ordered_ids = [e["service"]["id"] for e in radius["services"]]
    assert ordered_ids.index(hard_target) < ordered_ids.index(soft_target)


async def test_score_sums_edge_weights_along_a_mixed_criticality_path(
    client: AsyncClient,
) -> None:
    # a --(hard)--> b --(soft)--> c : edge_weight = 1.0 + 0.4 = 1.4 (summed, not averaged),
    # tier_weight(TIER_1) = 1.0, depth = 2 -> score = 1.4 * 1.0 / 2 = 0.7
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _my_workspace_id(client, token)

    a = await _create_service(client, token=token, workspace_id=workspace_id, name="a", tier=1)
    b = await _create_service(client, token=token, workspace_id=workspace_id, name="b", tier=1)
    c = await _create_service(client, token=token, workspace_id=workspace_id, name="c", tier=1)
    await _create_edge(
        client, token=token, workspace_id=workspace_id, from_id=a, to_id=b, criticality="hard"
    )
    await _create_edge(
        client, token=token, workspace_id=workspace_id, from_id=b, to_id=c, criticality="soft"
    )

    radius = await _blast_radius(
        client, token=token, workspace_id=workspace_id, service_id=a, depth=10
    )

    entry_for_c = next(e for e in radius["services"] if e["service"]["id"] == c)
    assert entry_for_c["score"] == 0.7
