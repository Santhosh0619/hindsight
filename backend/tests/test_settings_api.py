import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import WorkspaceMember, WorkspaceRole
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return str(response.json()["memberships"][0]["workspace_id"])


async def test_llm_test_reports_unconfigured_slots_without_calling_them(
    client: AsyncClient,
) -> None:
    # No LLM key is configured in this build session (standing choice since Phase 6) --
    # gemini/groq must report configured=false with no attempt made; ollama is always
    # "configured" (no key required) but its own reachability is independently real.
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/settings/llm/test", headers=auth_headers(token)
    )
    assert response.status_code == 200, response.text
    results = {r["provider"]: r for r in response.json()}

    assert results["gemini"]["configured"] is False
    assert results["gemini"]["ok"] is None
    assert results["gemini"]["error"] is None

    assert results["groq"]["configured"] is False
    assert results["groq"]["ok"] is None

    assert results["ollama"]["configured"] is True
    # Never raised as a 503 -- a failed connectivity check is the response body.
    assert results["ollama"]["ok"] is False
    assert results["ollama"]["latency_ms"] is not None
    assert results["ollama"]["error"] is not None


async def test_viewer_cannot_run_the_llm_test(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    me = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    user_id = me.json()["user"]["id"]
    member = await db.get(WorkspaceMember, (uuid.UUID(workspace_id), uuid.UUID(user_id)))
    assert member is not None
    member.role = WorkspaceRole.VIEWER
    await db.commit()

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/settings/llm/test", headers=auth_headers(token)
    )
    assert response.status_code == 403
