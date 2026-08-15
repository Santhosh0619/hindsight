import json
import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.models.workspace import WorkspaceMember, WorkspaceRole
from tests.conftest import auth_headers, signup, unique_email


async def _create_demo_guest(client: AsyncClient) -> dict[str, Any]:
    # A distinct X-Forwarded-For gives each guest its own demo_signup_bucket key,
    # isolated from every other test that also calls /auth/demo.
    headers = {"X-Forwarded-For": f"198.51.100.{uuid.uuid4().int % 250}"}
    response = await client.post("/api/v1/auth/demo", headers=headers)
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _workspace_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return str(response.json()["memberships"][0]["workspace_id"])


async def _create_incident(client: AsyncClient, token: str, workspace_id: str) -> str:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents",
        json={"title": "demo rbac test incident", "raw_alert_text": "checkout is throwing 500s"},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_demo_guest_can_create_incident_and_generate_and_stream_brief(
    client: AsyncClient,
) -> None:
    guest = await _create_demo_guest(client)
    token = guest["access_token"]
    workspace_id = await _workspace_id(client, token)

    incident_id = await _create_incident(client, token, workspace_id)

    brief_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/brief",
        headers=auth_headers(token),
    )
    assert brief_response.status_code == 200, brief_response.text

    events = []
    async with client.stream(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/brief/stream",
        headers=auth_headers(token),
    ) as stream_response:
        assert stream_response.status_code == 200
        async for line in stream_response.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :].strip()))
    assert events[-1]["type"] == "done"


async def test_owner_can_still_create_an_incident_under_owner_or_responder_or_demo(
    client: AsyncClient,
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    incident_id = await _create_incident(client, token, workspace_id)

    assert incident_id is not None


async def _demote_to_viewer(db: AsyncSession, workspace_id: str, user_id: str) -> None:
    member = await db.get(WorkspaceMember, (uuid.UUID(workspace_id), uuid.UUID(user_id)))
    assert member is not None
    member.role = WorkspaceRole.VIEWER
    await db.commit()


async def test_real_viewer_is_still_denied_incident_creation(
    client: AsyncClient,
) -> None:
    # A plain (non-demo) viewer must still be rejected by the widened dependency --
    # require_role_or_demo only carves out an exception for current_user.is_demo, it
    # does not loosen the role check for anyone else.
    owner = await signup(client, email=unique_email())
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    me = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    user_id = me.json()["user"]["id"]

    async with get_session_factory()() as db:
        await _demote_to_viewer(db, workspace_id, user_id)

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents",
        json={"title": "t", "raw_alert_text": "alert"},
        headers=auth_headers(token),
    )
    assert response.status_code == 403


async def test_demo_guest_is_denied_in_a_real_workspace_they_later_joined(
    client: AsyncClient,
) -> None:
    # A demo guest's is_demo flag is permanent on the account, not scoped to the demo
    # workspace -- require_role_or_demo must only carve out an exception when the
    # workspace being accessed is itself the demo workspace, or a demo guest who
    # joins a real workspace via invite code (then gets demoted like anyone else)
    # would keep write access the owner thought they'd revoked.
    owner = await signup(client)
    owner_token = owner["access_token"]
    real_workspace_id = await _workspace_id(client, owner_token)

    guest = await _create_demo_guest(client)
    guest_token = guest["access_token"]

    invite = await client.post(
        f"/api/v1/workspaces/{real_workspace_id}/members/invite-code",
        headers=auth_headers(owner_token),
    )
    assert invite.status_code == 200, invite.text
    join = await client.post(
        "/api/v1/workspaces/join",
        json={"code": invite.json()["code"]},
        headers=auth_headers(guest_token),
    )
    assert join.status_code == 200, join.text

    me = await client.get("/api/v1/auth/me", headers=auth_headers(guest_token))
    guest_user_id = me.json()["user"]["id"]
    async with get_session_factory()() as db:
        await _demote_to_viewer(db, real_workspace_id, guest_user_id)

    response = await client.post(
        f"/api/v1/workspaces/{real_workspace_id}/incidents",
        json={"title": "t", "raw_alert_text": "alert"},
        headers=auth_headers(guest_token),
    )
    assert response.status_code == 403


async def test_demo_brief_bucket_exhausts_after_capacity(client: AsyncClient) -> None:
    guest = await _create_demo_guest(client)
    token = guest["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(client, token, workspace_id)

    responses = [
        await client.post(
            f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/brief",
            headers=auth_headers(token),
        )
        for _ in range(11)
    ]

    assert [r.status_code for r in responses[:10]] == [200] * 10
    assert responses[10].status_code == 429
    assert responses[10].json()["error"]["code"] == "rate_limited"


async def test_demo_brief_bucket_does_not_apply_to_a_real_owner(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(client, token, workspace_id)

    responses = [
        await client.post(
            f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/brief",
            headers=auth_headers(token),
        )
        for _ in range(11)
    ]

    assert all(r.status_code == 200 for r in responses)
