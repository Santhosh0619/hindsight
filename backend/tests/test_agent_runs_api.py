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


async def _create_incident(client: AsyncClient, token: str, workspace_id: str) -> str:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents",
        json={"title": "t", "raw_alert_text": "checkout-api is throwing 500s"},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_empty_workspace_has_no_runs_and_a_null_cache_hit_rate(
    client: AsyncClient,
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    runs_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/agent-runs", headers=auth_headers(token)
    )
    assert runs_response.status_code == 200
    assert runs_response.json()["items"] == []

    stats_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/agent-runs/stats", headers=auth_headers(token)
    )
    stats = stats_response.json()
    assert stats["total_runs"] == 0
    # Never a misleading 0.0 with nothing to compute a rate from.
    assert stats["cache_hit_rate"] is None


async def test_generating_a_brief_writes_a_real_step_waterfall(client: AsyncClient) -> None:
    """The regression test for the real bug this phase fixed: the non-streaming
    POST .../brief endpoint used to call graph.ainvoke directly and never wrote any
    AgentRunStep rows at all."""
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(client, token, workspace_id)

    brief_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/brief",
        headers=auth_headers(token),
    )
    assert brief_response.status_code == 200, brief_response.text

    runs_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/agent-runs", headers=auth_headers(token)
    )
    runs = runs_response.json()["items"]
    assert len(runs) == 1
    run = runs[0]
    assert run["incident_id"] == incident_id
    assert run["status"] == "done"
    # No LLM key configured in this build -- honestly zero, not missing.
    assert run["total_tokens_in"] == 0
    assert run["total_tokens_out"] == 0
    assert run["from_cache"] is False

    detail_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/agent-runs/{run['id']}", headers=auth_headers(token)
    )
    assert detail_response.status_code == 200
    steps = detail_response.json()["steps"]
    node_names = [s["node_name"] for s in steps]
    assert node_names == ["normalizer", "retriever", "correlator", "analyst", "critic", "briefer"]
    for step in steps:
        assert step["status"] == "done"
        assert step["tokens_in"] == 0
        assert step["tokens_out"] == 0

    # The step-level summary enrichment (FR-01/FR-06): each node's own summary shape,
    # not just "which keys changed".
    retriever_step = next(s for s in steps if s["node_name"] == "retriever")
    assert "result_count" in retriever_step["output_summary"]
    correlator_step = next(s for s in steps if s["node_name"] == "correlator")
    assert "candidate_count" in correlator_step["output_summary"]
    analyst_step = next(s for s in steps if s["node_name"] == "analyst")
    assert "hypothesis_count" in analyst_step["output_summary"]
    critic_step = next(s for s in steps if s["node_name"] == "critic")
    assert "score" in critic_step["output_summary"]

    stats_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/agent-runs/stats", headers=auth_headers(token)
    )
    stats = stats_response.json()
    assert stats["total_runs"] == 1
    assert stats["cache_hit_rate"] == 0.0


async def test_agent_run_detail_404s_across_workspaces(client: AsyncClient) -> None:
    owner_a = await signup(client)
    owner_b = await signup(client)
    workspace_a = await _workspace_id(client, owner_a["access_token"])
    workspace_b = await _workspace_id(client, owner_b["access_token"])
    incident_id = await _create_incident(client, owner_a["access_token"], workspace_a)
    brief_response = await client.post(
        f"/api/v1/workspaces/{workspace_a}/incidents/{incident_id}/brief",
        headers=auth_headers(owner_a["access_token"]),
    )
    assert brief_response.status_code == 200
    run_id = (
        await client.get(
            f"/api/v1/workspaces/{workspace_a}/agent-runs",
            headers=auth_headers(owner_a["access_token"]),
        )
    ).json()["items"][0]["id"]

    response = await client.get(
        f"/api/v1/workspaces/{workspace_b}/agent-runs/{run_id}",
        headers=auth_headers(owner_b["access_token"]),
    )
    assert response.status_code == 404


async def test_viewer_can_read_agent_runs(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    await _demote_to_viewer(client, db, workspace_id, token)

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/agent-runs", headers=auth_headers(token)
    )
    assert response.status_code == 200

    stats_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/agent-runs/stats", headers=auth_headers(token)
    )
    assert stats_response.status_code == 200
