import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Brief, BriefStatus, Incident, IncidentSignal
from app.models.postmortem import Postmortem, PostmortemStatus
from app.services import dashboard_service
from app.services.postgres_graph_store import PostgresGraphStore
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return uuid.UUID(response.json()["memberships"][0]["workspace_id"])


async def _create_service(client: AsyncClient, token: str, workspace_id: uuid.UUID) -> uuid.UUID:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": f"svc-{uuid.uuid4().hex[:8]}", "tier": 1},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def _incident(
    *, workspace_id: uuid.UUID, opened_at: datetime, resolved_at: datetime | None, status: str
) -> Incident:
    return Incident(
        workspace_id=workspace_id,
        title="t",
        raw_alert_text="alert",
        status=status,
        opened_at=opened_at,
        resolved_at=resolved_at,
    )


async def test_empty_workspace_returns_zeros_and_no_null_faking(client: AsyncClient) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/dashboard", headers=auth_headers(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["open_incidents"] == 0
    assert body["briefs_generated"] == 0
    assert body["corpus_size"] == 0
    assert body["fragile_services"] == []
    assert body["recent_briefs"] == []
    assert len(body["mttr_trend"]) == 8
    assert all(point["mttr_minutes"] is None for point in body["mttr_trend"])


async def test_open_incidents_counts_only_open_status(
    db: AsyncSession, client: AsyncClient
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    now = datetime.now(UTC)

    db.add(_incident(workspace_id=workspace_id, opened_at=now, resolved_at=None, status="open"))
    db.add(_incident(workspace_id=workspace_id, opened_at=now, resolved_at=None, status="open"))
    db.add(_incident(workspace_id=workspace_id, opened_at=now, resolved_at=now, status="resolved"))
    await db.commit()

    store = PostgresGraphStore(db)
    result = await dashboard_service.get_dashboard(db, store, workspace_id=workspace_id)
    assert result.open_incidents == 2


async def test_ingest_health_counts_postmortems_by_status(
    db: AsyncSession, client: AsyncClient
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    for status in (
        PostmortemStatus.INDEXED,
        PostmortemStatus.INDEXED,
        PostmortemStatus.FAILED,
        PostmortemStatus.PENDING,
    ):
        db.add(
            Postmortem(
                workspace_id=workspace_id,
                title="pm",
                raw_text="Summary:\nsomething\n",
                status=status,
            )
        )
    await db.commit()

    store = PostgresGraphStore(db)
    result = await dashboard_service.get_dashboard(db, store, workspace_id=workspace_id)
    assert result.ingest_health.indexed == 2
    assert result.ingest_health.failed == 1
    assert result.ingest_health.pending == 1
    assert result.ingest_health.processing == 0
    assert result.corpus_size == 4


async def test_briefs_generated_and_recent_briefs_are_workspace_scoped(
    db: AsyncSession, client: AsyncClient
) -> None:
    owner_a = await signup(client)
    token_a = owner_a["access_token"]
    workspace_a = await _workspace_id(client, token_a)

    owner_b = await signup(client)
    token_b = owner_b["access_token"]
    workspace_b = await _workspace_id(client, token_b)

    now = datetime.now(UTC)
    incident_a = _incident(workspace_id=workspace_a, opened_at=now, resolved_at=None, status="open")
    incident_b = _incident(workspace_id=workspace_b, opened_at=now, resolved_at=None, status="open")
    db.add(incident_a)
    db.add(incident_b)
    await db.commit()

    db.add(
        Brief(
            incident_id=incident_a.id,
            version=1,
            status=BriefStatus.READY,
            overall_confidence=0.7,
            generated_at=now,
        )
    )
    db.add(
        Brief(
            incident_id=incident_b.id,
            version=1,
            status=BriefStatus.READY,
            overall_confidence=0.9,
            generated_at=now,
        )
    )
    await db.commit()

    store = PostgresGraphStore(db)
    result_a = await dashboard_service.get_dashboard(db, store, workspace_id=workspace_a)
    assert result_a.briefs_generated == 1
    assert len(result_a.recent_briefs) == 1
    assert result_a.recent_briefs[0].incident_id == incident_a.id


async def test_mttr_trend_buckets_by_resolution_week_and_excludes_incidents_outside_the_window(
    db: AsyncSession, client: AsyncClient
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    now = datetime.now(UTC)

    # Resolved just now: opened 2 hours before resolution -- lands in the current
    # week's bucket with a real, non-zero MTTR.
    db.add(
        _incident(
            workspace_id=workspace_id,
            opened_at=now - timedelta(hours=2),
            resolved_at=now,
            status="resolved",
        )
    )
    # Resolved 20 weeks ago -- well outside the 8-week trend window, must not appear
    # in any bucket (and must not skew the total average either).
    far_past = now - timedelta(weeks=20)
    db.add(
        _incident(
            workspace_id=workspace_id,
            opened_at=far_past - timedelta(hours=1),
            resolved_at=far_past,
            status="resolved",
        )
    )
    await db.commit()

    store = PostgresGraphStore(db)
    result = await dashboard_service.get_dashboard(db, store, workspace_id=workspace_id)
    assert len(result.mttr_trend) == 8
    current_week_point = result.mttr_trend[-1]
    assert current_week_point.mttr_minutes is not None
    assert 100 < current_week_point.mttr_minutes < 140  # ~2 hours = 120 minutes
    # Every other bucket is null -- the far-past incident landed in none of them.
    assert all(p.mttr_minutes is None for p in result.mttr_trend[:-1])


async def test_fragile_services_ranks_by_incident_count_and_blast_radius(
    db: AsyncSession, client: AsyncClient
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    upstream_id = await _create_service(client, token, workspace_id)
    downstream_id = await _create_service(client, token, workspace_id)
    lonely_id = await _create_service(client, token, workspace_id)

    edge_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/edges",
        json={
            "from_service_id": str(upstream_id),
            "to_service_id": str(downstream_id),
            "kind": "calls",
            "criticality": "hard",
        },
        headers=auth_headers(token),
    )
    assert edge_response.status_code == 201, edge_response.text

    now = datetime.now(UTC)
    for _ in range(3):
        incident = _incident(
            workspace_id=workspace_id, opened_at=now, resolved_at=None, status="open"
        )
        db.add(incident)
        await db.flush()
        db.add(IncidentSignal(incident_id=incident.id, affected_service_ids=[upstream_id]))
    await db.commit()

    store = PostgresGraphStore(db)
    result = await dashboard_service.get_dashboard(db, store, workspace_id=workspace_id)

    by_id = {fs.service.id: fs for fs in result.fragile_services}
    upstream = by_id[upstream_id]
    lonely = by_id[lonely_id]

    assert upstream.incident_count == 3
    assert upstream.blast_radius_size >= 1  # reaches downstream_id
    assert upstream.fragility_score == 3 * (1 + upstream.blast_radius_size)
    assert lonely.incident_count == 0
    assert lonely.fragility_score == 0
    # Ranked: the service with real incidents and a wider blast radius sorts first.
    assert result.fragile_services[0].service.id == upstream_id
