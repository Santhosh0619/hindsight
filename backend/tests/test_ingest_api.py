from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers import queue
from app.workers.handlers.ingest_postmortem import handle_ingest_postmortem
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return str(response.json()["memberships"][0]["workspace_id"])


async def _create_key(client: AsyncClient, token: str, workspace_id: str) -> str:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/apikeys",
        json={"name": "ci-bot"},
        headers=auth_headers(token),
    )
    raw_key: str = response.json()["raw_key"]
    return raw_key


async def test_the_full_checkpoint_create_ingest_revoke_401(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The literal Master-Prompt.md checkpoint: create an API key, POST a postmortem
    with it, watch it ingest, revoke the key, confirm the next request 401s."""
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    raw_key = await _create_key(client, token, workspace_id)

    ingest_response = await client.post(
        "/api/v1/ingest/postmortem",
        json={
            "title": "webhook postmortem",
            "raw_text": "Summary:\nA service pushed via the ingest webhook.\n",
        },
        headers={"X-API-Key": raw_key},
    )
    assert ingest_response.status_code == 201, ingest_response.text
    postmortem_id = ingest_response.json()["id"]
    assert ingest_response.json()["status"] == "pending"

    # Same real worker path any session-created postmortem goes through.
    jobs = await queue.claim(db, worker_id="test-worker", kinds=["ingest_postmortem"], limit=50)
    assert len(jobs) == 1
    await handle_ingest_postmortem(db, jobs[0])
    await queue.complete(db, job=jobs[0])
    extract_jobs = await queue.claim(
        db, worker_id="test-worker", kinds=["extract_postmortem"], limit=50
    )
    for job in extract_jobs:
        await queue.complete(db, job=job)

    status_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/postmortems/{postmortem_id}/status",
        headers=auth_headers(token),
    )
    assert status_response.json()["status"] == "indexed"

    keys = (
        await client.get(f"/api/v1/workspaces/{workspace_id}/apikeys", headers=auth_headers(token))
    ).json()
    revoke_response = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/apikeys/{keys[0]['id']}", headers=auth_headers(token)
    )
    assert revoke_response.status_code == 204

    post_revoke_response = await client.post(
        "/api/v1/ingest/postmortem",
        json={"title": "should fail", "raw_text": "Summary:\nshould not ingest.\n"},
        headers={"X-API-Key": raw_key},
    )
    assert post_revoke_response.status_code == 401


async def test_missing_api_key_header_401s(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/ingest/postmortem",
        json={"title": "t", "raw_text": "Summary:\nno key at all.\n"},
    )
    assert response.status_code == 401


async def test_unknown_api_key_401s(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/ingest/postmortem",
        json={"title": "t", "raw_text": "Summary:\nfake key.\n"},
        headers={"X-API-Key": "hs_not-a-real-key"},
    )
    assert response.status_code == 401


async def test_ingest_resolves_the_correct_workspace_not_another_ones(
    client: AsyncClient,
) -> None:
    owner_a = await signup(client)
    owner_b = await signup(client)
    workspace_a = await _workspace_id(client, owner_a["access_token"])
    workspace_b = await _workspace_id(client, owner_b["access_token"])
    raw_key_a = await _create_key(client, owner_a["access_token"], workspace_a)

    ingest_response = await client.post(
        "/api/v1/ingest/postmortem",
        json={"title": "belongs to a", "raw_text": "Summary:\nshould land in workspace A.\n"},
        headers={"X-API-Key": raw_key_a},
    )
    assert ingest_response.status_code == 201

    # workspace B's own postmortem list must not see it.
    listed_b = await client.get(
        f"/api/v1/workspaces/{workspace_b}/postmortems",
        headers=auth_headers(owner_b["access_token"]),
    )
    titles_b = {item["title"] for item in listed_b.json()["items"]}
    assert "belongs to a" not in titles_b

    listed_a = await client.get(
        f"/api/v1/workspaces/{workspace_a}/postmortems",
        headers=auth_headers(owner_a["access_token"]),
    )
    titles_a = {item["title"] for item in listed_a.json()["items"]}
    assert "belongs to a" in titles_a
