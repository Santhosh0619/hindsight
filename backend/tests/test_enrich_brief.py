import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Brief, BriefStatus, Incident
from app.models.postmortem import PostmortemChunk
from app.services.incidents_service import _enrich_brief
from app.workers import queue
from app.workers.handlers.ingest_postmortem import handle_ingest_postmortem
from tests.conftest import auth_headers, signup

_PM_TEXT = "Summary:\ncheckout-api failed due to ORA-12520 connection pool exhaustion.\n"


async def _workspace_id(client: AsyncClient, token: str) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return uuid.UUID(response.json()["memberships"][0]["workspace_id"])


async def _ingest(
    client: AsyncClient, db: AsyncSession, *, token: str, workspace_id: uuid.UUID
) -> uuid.UUID:
    create_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/postmortems",
        json={"title": "checkout-api pool exhaustion", "raw_text": _PM_TEXT},
        headers=auth_headers(token),
    )
    postmortem_id = uuid.UUID(create_response.json()["id"])
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


async def _one_chunk_id(db: AsyncSession, postmortem_id: uuid.UUID) -> uuid.UUID:
    result = await db.execute(
        select(PostmortemChunk.id).where(PostmortemChunk.postmortem_id == postmortem_id)
    )
    return result.scalars().first()


async def test_enrich_brief_drops_a_hypothesis_whose_only_citation_no_longer_resolves(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    postmortem_id = await _ingest(client, db, token=token, workspace_id=workspace_id)
    real_chunk_id = await _one_chunk_id(db, postmortem_id)

    incident = Incident(
        workspace_id=workspace_id,
        title="enrich test incident",
        raw_alert_text="alert",
        opened_at=datetime.now(UTC),
    )
    db.add(incident)
    await db.commit()

    dangling_chunk_id = uuid.uuid4()
    dangling_postmortem_id = uuid.uuid4()
    real_citation = {
        "chunk_id": str(real_chunk_id),
        "postmortem_id": str(postmortem_id),
        "quote": None,
    }
    dangling_citation = {
        "chunk_id": str(dangling_chunk_id),
        "postmortem_id": str(dangling_postmortem_id),
        "quote": None,
    }

    brief_row = Brief(
        incident_id=incident.id,
        version=1,
        status=BriefStatus.READY,
        hypotheses=[
            {"statement": "grounded claim", "confidence": 0.8, "citations": [real_citation]},
            {"statement": "ungrounded claim", "confidence": 0.5, "citations": [dangling_citation]},
        ],
        matched_postmortems=[
            {
                "postmortem_id": str(postmortem_id),
                "vector_score": 0.8,
                "keyword_score": 0.0,
                "graph_score": 0.0,
                "failure_mode_overlap": 0.0,
                "recency": 1.0,
                "overall_score": 0.36,
                "rank": 1,
            },
            {
                "postmortem_id": str(dangling_postmortem_id),
                "vector_score": 0.1,
                "keyword_score": 0.0,
                "graph_score": 0.0,
                "failure_mode_overlap": 0.0,
                "recency": 0.2,
                "overall_score": 0.06,
                "rank": 2,
            },
        ],
        blast_radius={"entries": []},
        runbook_steps=[
            {
                "step": "restart the pool manager",
                "source_postmortem_id": None,
                "citation": dangling_citation,
            },
        ],
        citations=[real_citation, dangling_citation],
        overall_confidence=0.65,
        correction_passes=0,
        llm_used=True,
        from_cache=False,
        generated_at=datetime.now(UTC),
    )
    db.add(brief_row)
    await db.commit()

    enriched = await _enrich_brief(db, brief_row)

    assert len(enriched.hypotheses) == 1
    assert enriched.hypotheses[0].statement == "grounded claim"
    assert enriched.hypotheses[0].citations[0].postmortem_title == "checkout-api pool exhaustion"
    assert "ORA-12520" in enriched.hypotheses[0].citations[0].content

    assert len(enriched.citations) == 1
    assert enriched.citations[0].chunk_id == real_chunk_id

    assert len(enriched.matched_postmortems) == 1
    assert enriched.matched_postmortems[0].postmortem.id == postmortem_id

    assert len(enriched.runbook_steps) == 1
    assert enriched.runbook_steps[0].citation is None
    assert enriched.runbook_steps[0].step == "restart the pool manager"
