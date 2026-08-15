import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import EvalCase, EvalCaseResult, EvalRun
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return uuid.UUID(response.json()["memberships"][0]["workspace_id"])


async def _seed_run(
    db: AsyncSession, *, workspace_id: uuid.UUID, mode: str = "full"
) -> tuple[EvalRun, EvalCase]:
    case = EvalCase(
        workspace_id=workspace_id,
        name="case-a",
        incident_text="some alert text",
        expected_postmortem_ids=[],
        expected_service_ids=[],
    )
    db.add(case)
    await db.flush()

    run = EvalRun(
        workspace_id=workspace_id,
        mode=mode,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        recall_at_1=0.5,
        recall_at_5=1.0,
        mrr=0.75,
        groundedness=None,
        citation_validity=1.0,
        cases_run=1,
    )
    db.add(run)
    await db.flush()

    db.add(
        EvalCaseResult(
            eval_run_id=run.id,
            eval_case_id=case.id,
            retrieved_ids=[],
            rank_of_first_hit=2,
            groundedness=None,
            passed=True,
        )
    )
    await db.commit()
    return run, case


async def test_list_eval_runs_returns_workspace_scoped_runs(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    run, _ = await _seed_run(db, workspace_id=workspace_id)

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/evaluation/runs", headers=auth_headers(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(run.id)
    assert body[0]["mode"] == "full"
    assert body[0]["recall_at_5"] == 1.0


async def test_get_eval_run_detail_includes_case_results(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    run, case = await _seed_run(db, workspace_id=workspace_id)

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/evaluation/runs/{run.id}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(run.id)
    assert len(body["results"]) == 1
    assert body["results"][0]["eval_case_id"] == str(case.id)
    assert body["results"][0]["case_name"] == "case-a"
    assert body["results"][0]["rank_of_first_hit"] == 2


async def test_get_eval_run_detail_404s_for_unknown_run(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/evaluation/runs/{uuid.uuid4()}",
        headers=auth_headers(token),
    )
    assert response.status_code == 404


async def test_get_eval_run_detail_404s_across_workspaces(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner_a = await signup(client)
    token_a = owner_a["access_token"]
    workspace_a = await _workspace_id(client, token_a)
    run, _ = await _seed_run(db, workspace_id=workspace_a)

    owner_b = await signup(client)
    token_b = owner_b["access_token"]
    workspace_b = await _workspace_id(client, token_b)

    response = await client.get(
        f"/api/v1/workspaces/{workspace_b}/evaluation/runs/{run.id}",
        headers=auth_headers(token_b),
    )
    assert response.status_code == 404


async def test_list_eval_runs_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/workspaces/{uuid.uuid4()}/evaluation/runs")
    assert response.status_code == 401


async def test_viewer_can_read_eval_runs(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    owner_token = owner["access_token"]
    workspace_id = await _workspace_id(client, owner_token)
    await _seed_run(db, workspace_id=workspace_id)

    invite_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/members/invite-code", headers=auth_headers(owner_token)
    )
    code = invite_response.json()["code"]

    viewer = await signup(client)
    viewer_token = viewer["access_token"]
    join_response = await client.post(
        "/api/v1/workspaces/join", json={"code": code}, headers=auth_headers(viewer_token)
    )
    assert join_response.status_code == 200, join_response.text
    viewer_user_id = viewer["user"]["id"]

    demote_response = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{viewer_user_id}",
        json={"role": "viewer"},
        headers=auth_headers(owner_token),
    )
    assert demote_response.status_code == 200, demote_response.text

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/evaluation/runs", headers=auth_headers(viewer_token)
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
