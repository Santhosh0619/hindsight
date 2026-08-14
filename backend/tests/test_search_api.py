import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postmortem import PostmortemService, ServiceLinkRole
from app.workers import queue
from app.workers.handlers.ingest_postmortem import handle_ingest_postmortem
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    workspace_id: str = response.json()["memberships"][0]["workspace_id"]
    return workspace_id


async def _ingest(
    client: AsyncClient, db: AsyncSession, *, token: str, workspace_id: str, raw_text: str
) -> str:
    create_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/postmortems",
        json={"title": "pm", "raw_text": raw_text},
        headers=auth_headers(token),
    )
    postmortem_id: str = create_response.json()["id"]

    jobs = await queue.claim(db, worker_id="test-worker", kinds=["ingest_postmortem"], limit=50)
    for job in jobs:
        await handle_ingest_postmortem(db, job)
        await queue.complete(db, job=job)
    extract_jobs = await queue.claim(
        db, worker_id="test-worker", kinds=["extract_postmortem"], limit=50
    )
    for job in extract_jobs:
        await queue.complete(db, job=job)

    return postmortem_id


async def _build_fixture_workspace(
    client: AsyncClient, db: AsyncSession, *, token: str, workspace_id: str
) -> dict[str, str]:
    checkout = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": "checkout-api", "tier": 1},
        headers=auth_headers(token),
    )
    payments = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": "payments-svc", "tier": 1},
        headers=auth_headers(token),
    )
    checkout_id = checkout.json()["id"]
    payments_id = payments.json()["id"]
    await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/edges",
        json={
            "from_service_id": checkout_id,
            "to_service_id": payments_id,
            "kind": "calls",
            "criticality": "hard",
        },
        headers=auth_headers(token),
    )

    vector_pm = await _ingest(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text=(
            "Summary:\nOur database ran completely out of available connections "
            "during peak traffic.\n"
        ),
    )
    keyword_pm = await _ingest(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text="Summary:\nORA-12520: TNS listener could not find available handler.\n",
    )
    graph_pm = await _ingest(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text="Summary:\npayments-svc rejected transactions after a bad deploy.\n",
    )
    db.add(
        PostmortemService(
            postmortem_id=uuid.UUID(graph_pm),
            service_id=uuid.UUID(payments_id),
            role=ServiceLinkRole.ROOT_CAUSE,
        )
    )
    await db.commit()

    return {"vector_pm": vector_pm, "keyword_pm": keyword_pm, "graph_pm": graph_pm}


async def test_the_four_modes_return_visibly_different_result_sets(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    fixture = await _build_fixture_workspace(client, db, token=token, workspace_id=workspace_id)

    vector_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/search",
        params={"q": "connection pool exhausted", "mode": "vector"},
        headers=auth_headers(token),
    )
    keyword_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/search",
        params={"q": "ORA-12520", "mode": "keyword"},
        headers=auth_headers(token),
    )
    graph_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/search",
        params={"q": "checkout-api", "mode": "graph"},
        headers=auth_headers(token),
    )

    assert vector_response.status_code == 200, vector_response.text
    assert keyword_response.status_code == 200, keyword_response.text
    assert graph_response.status_code == 200, graph_response.text

    vector_ids = {r["postmortem"]["id"] for r in vector_response.json()["results"]}
    keyword_ids = {r["postmortem"]["id"] for r in keyword_response.json()["results"]}
    graph_ids = {r["postmortem"]["id"] for r in graph_response.json()["results"]}

    assert fixture["vector_pm"] in vector_ids
    assert fixture["keyword_pm"] in keyword_ids
    assert fixture["graph_pm"] in graph_ids
    assert vector_ids != keyword_ids
    assert keyword_ids != graph_ids


async def test_hybrid_mode_reports_accurate_source_attribution(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    fixture = await _build_fixture_workspace(client, db, token=token, workspace_id=workspace_id)

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/search",
        params={"q": "checkout-api", "mode": "hybrid"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["mode"] == "hybrid"
    assert set(body["timings_ms"]) == {"vector", "keyword", "graph", "fusion"}

    graph_result = next(r for r in body["results"] if r["postmortem"]["id"] == fixture["graph_pm"])
    sources = {s["source"] for s in graph_result["sources"]}
    assert sources == {"graph"}
    assert graph_result["graph_reason"]["matched_service_name"] == "checkout-api"
    assert graph_result["graph_reason"]["via_service_name"] == "payments-svc"


async def test_empty_query_is_rejected(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/search",
        params={"q": ""},
        headers=auth_headers(token),
    )

    assert response.status_code == 422


async def test_whitespace_only_query_is_rejected(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    # "   " passes FastAPI's own min_length=1 check (length 3), so this specifically
    # exercises the route's own strip-and-check rather than Pydantic's Query validator.
    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/search",
        params={"q": "   "},
        headers=auth_headers(token),
    )

    assert response.status_code == 422


async def test_non_member_gets_404(client: AsyncClient) -> None:
    owner = await signup(client)
    outsider = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/search",
        params={"q": "anything"},
        headers=auth_headers(outsider["access_token"]),
    )

    assert response.status_code == 404


async def test_search_never_returns_another_workspaces_postmortems(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner_a = await signup(client)
    owner_b = await signup(client)
    token_a = owner_a["access_token"]
    token_b = owner_b["access_token"]
    workspace_a = await _workspace_id(client, token_a)
    workspace_b = await _workspace_id(client, token_b)

    pm_a = await _ingest(
        client,
        db,
        token=token_a,
        workspace_id=workspace_a,
        raw_text="Summary:\nA distinctive cross-tenant search fixture phrase.\n",
    )

    response = await client.get(
        f"/api/v1/workspaces/{workspace_b}/search",
        params={"q": "distinctive cross-tenant search fixture phrase", "mode": "keyword"},
        headers=auth_headers(token_b),
    )

    assert response.status_code == 200
    result_ids = {r["postmortem"]["id"] for r in response.json()["results"]}
    assert pm_a not in result_ids


async def test_graph_and_hybrid_mode_never_leak_across_workspaces_with_same_service_name(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner_a = await signup(client)
    owner_b = await signup(client)
    token_a = owner_a["access_token"]
    token_b = owner_b["access_token"]
    workspace_a = await _workspace_id(client, token_a)
    workspace_b = await _workspace_id(client, token_b)

    # Both workspaces independently name a service "shared-svc" -- distinct rows,
    # same name, the realistic near-miss case for a workspace_id-scoping bug.
    service_a = await client.post(
        f"/api/v1/workspaces/{workspace_a}/catalog/services",
        json={"name": "shared-svc", "tier": 1},
        headers=auth_headers(token_a),
    )
    await client.post(
        f"/api/v1/workspaces/{workspace_b}/catalog/services",
        json={"name": "shared-svc", "tier": 1},
        headers=auth_headers(token_b),
    )

    pm_a = await _ingest(
        client,
        db,
        token=token_a,
        workspace_id=workspace_a,
        raw_text="Summary:\nshared-svc had an outage in workspace A.\n",
    )
    db.add(
        PostmortemService(
            postmortem_id=uuid.UUID(pm_a),
            service_id=uuid.UUID(service_a.json()["id"]),
            role=ServiceLinkRole.ROOT_CAUSE,
        )
    )
    await db.commit()

    for mode in ("graph", "hybrid"):
        response = await client.get(
            f"/api/v1/workspaces/{workspace_b}/search",
            params={"q": "shared-svc", "mode": mode},
            headers=auth_headers(token_b),
        )
        assert response.status_code == 200, response.text
        result_ids = {r["postmortem"]["id"] for r in response.json()["results"]}
        assert pm_a not in result_ids
