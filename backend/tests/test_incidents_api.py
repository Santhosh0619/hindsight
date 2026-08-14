import json
import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Brief, BriefStatus, FeedbackVerdict
from app.models.workspace import WorkspaceMember, WorkspaceRole
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return str(response.json()["memberships"][0]["workspace_id"])


async def _create_incident(
    client: AsyncClient, token: str, workspace_id: str, title: str = "t"
) -> str:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents",
        json={"title": title, "raw_alert_text": "checkout-api is throwing 500s"},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _demote_to_viewer(
    client: AsyncClient, db: AsyncSession, workspace_id: str, token: str
) -> None:
    me = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    user_id = me.json()["user"]["id"]
    member = await db.get(WorkspaceMember, (uuid.UUID(workspace_id), uuid.UUID(user_id)))
    assert member is not None
    member.role = WorkspaceRole.VIEWER
    await db.commit()


async def test_create_and_get_incident(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    incident_id = await _create_incident(client, token, workspace_id, title="db saturation")

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}", headers=auth_headers(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "db saturation"
    assert body["status"] == "open"
    assert body["resolved_at"] is None


async def test_viewer_cannot_create_an_incident(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    await _demote_to_viewer(client, db, workspace_id, token)

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents",
        json={"title": "t", "raw_alert_text": "alert"},
        headers=auth_headers(token),
    )
    assert response.status_code == 403


async def test_list_incidents_filters_by_status(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    open_id = await _create_incident(client, token, workspace_id, title="open one")
    resolved_id = await _create_incident(client, token, workspace_id, title="resolved one")
    await client.patch(
        f"/api/v1/workspaces/{workspace_id}/incidents/{resolved_id}",
        json={"status": "resolved"},
        headers=auth_headers(token),
    )

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/incidents",
        params={"status": "open"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert open_id in ids
    assert resolved_id not in ids


async def test_patch_sets_resolved_at_on_transition_to_resolved(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(client, token, workspace_id)

    response = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}",
        json={"status": "resolved"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None


async def test_reopening_a_resolved_incident_does_not_clear_resolved_at(
    client: AsyncClient,
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(client, token, workspace_id)
    await client.patch(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}",
        json={"status": "resolved"},
        headers=auth_headers(token),
    )

    reopened = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}",
        json={"status": "open"},
        headers=auth_headers(token),
    )
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is not None


async def test_incidents_never_leak_across_workspaces(client: AsyncClient) -> None:
    owner_a = await signup(client)
    owner_b = await signup(client)
    workspace_a = await _workspace_id(client, owner_a["access_token"])
    workspace_b = await _workspace_id(client, owner_b["access_token"])
    incident_a = await _create_incident(client, owner_a["access_token"], workspace_a)

    response = await client.get(
        f"/api/v1/workspaces/{workspace_b}/incidents/{incident_a}",
        headers=auth_headers(owner_b["access_token"]),
    )
    assert response.status_code == 404


async def test_generating_a_brief_with_no_llm_configured_still_returns_a_deterministic_brief(
    client: AsyncClient,
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(client, token, workspace_id)

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/brief",
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["llm_used"] is False
    assert body["version"] == 1
    assert body["correction_passes"] == 0

    listed = await client.get(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/briefs",
        headers=auth_headers(token),
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_stream_brief_endpoint_returns_a_real_sse_event_sequence(
    client: AsyncClient,
) -> None:
    # Exercises the real HTTP/ASGI route, not incidents_service directly -- this is
    # the layer where a request-scoped DB session closing before the generator body
    # actually runs would otherwise go unnoticed (see ADR).
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(client, token, workspace_id)

    events = []
    async with client.stream(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/brief/stream",
        headers=auth_headers(token),
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :].strip()))

    event_types = [e["type"] for e in events]
    assert event_types[0] == "node_start"
    assert event_types[-1] == "done"
    assert events[-1]["brief_id"] is not None


async def test_feedback_requires_the_brief_to_belong_to_the_named_incident(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_a = await _create_incident(client, token, workspace_id, title="a")
    incident_b = await _create_incident(client, token, workspace_id, title="b")

    brief = Brief(
        incident_id=uuid.UUID(incident_a),
        version=1,
        status=BriefStatus.READY,
        llm_used=False,
        generated_at=datetime.now(UTC),
    )
    db.add(brief)
    await db.commit()

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_b}/brief/{brief.id}/feedback",
        json={"verdict": "helpful"},
        headers=auth_headers(token),
    )
    assert response.status_code == 404


async def test_submit_feedback(client: AsyncClient, db: AsyncSession) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(client, token, workspace_id)

    brief = Brief(
        incident_id=uuid.UUID(incident_id),
        version=1,
        status=BriefStatus.READY,
        llm_used=False,
        generated_at=datetime.now(UTC),
    )
    db.add(brief)
    await db.commit()

    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/brief/{brief.id}/feedback",
        json={"verdict": "unhelpful", "note": "missed the real cause"},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verdict"] == FeedbackVerdict.UNHELPFUL.value
    assert body["note"] == "missed the real cause"


async def test_non_member_gets_404_on_incident_list(client: AsyncClient) -> None:
    owner = await signup(client)
    outsider = await signup(client)
    workspace_id = await _workspace_id(client, owner["access_token"])

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/incidents",
        headers=auth_headers(outsider["access_token"]),
    )
    assert response.status_code == 404
