import uuid
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident
from app.models.postmortem import PostmortemChunk
from app.services import incidents_service
from app.services.llm.router import LLMRouter
from app.services.postgres_graph_store import PostgresGraphStore
from app.workers import queue
from app.workers.handlers.ingest_postmortem import handle_ingest_postmortem
from tests.conftest import FakeModelProvider, auth_headers, signup

_PM_TEXT = "Summary:\ncheckout-api failed due to ORA-12520 connection pool exhaustion.\n"


async def _workspace_id(client: AsyncClient, token: str) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return uuid.UUID(response.json()["memberships"][0]["workspace_id"])


async def _create_service(
    client: AsyncClient, token: str, workspace_id: uuid.UUID, name: str
) -> None:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": name, "tier": 1},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text


async def _ingest(
    client: AsyncClient, db: AsyncSession, *, token: str, workspace_id: uuid.UUID, raw_text: str
) -> uuid.UUID:
    create_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/postmortems",
        json={"title": "checkout-api pool exhaustion", "raw_text": raw_text},
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


async def _create_incident(db: AsyncSession, *, workspace_id: uuid.UUID, raw_text: str) -> Incident:
    incident = Incident(
        workspace_id=workspace_id,
        title="service test incident",
        raw_alert_text=raw_text,
        opened_at=datetime.now(UTC),
    )
    db.add(incident)
    await db.commit()
    return incident


def _function_model(*, signal_fn: Any, draft_fn: Any, judgment_fn: Any) -> FunctionModel:
    def fn(_messages: list[Any], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        props = set(tool.parameters_json_schema.get("properties", {}).keys())
        if "candidate_service_names" in props:
            args = signal_fn()
        elif "hypotheses" in props:
            args = draft_fn()
        elif "is_grounded" in props:
            args = judgment_fn()
        else:
            raise AssertionError(f"unexpected output schema: {sorted(props)}")
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])

    return FunctionModel(fn)


async def test_generate_brief_enriches_citations_with_real_chunk_content_and_postmortem_titles(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    await _create_service(client, token, workspace_id, "checkout-api")
    postmortem_id = await _ingest(
        client, db, token=token, workspace_id=workspace_id, raw_text=_PM_TEXT
    )
    chunk_id = await _one_chunk_id(db, postmortem_id)
    incident = await _create_incident(
        db, workspace_id=workspace_id, raw_text="checkout-api pool exhaustion errors"
    )

    def signal_args() -> dict[str, Any]:
        return {
            "symptoms": ["checkout errors"],
            "error_strings": ["ORA-12520"],
            "metrics": {},
            "candidate_service_names": ["checkout-api"],
            "time_window": None,
            "severity_guess": "sev2",
            "extraction_confidence": 0.9,
        }

    def draft_args() -> dict[str, Any]:
        citation = {"chunk_id": str(chunk_id), "postmortem_id": str(postmortem_id), "quote": None}
        return {
            "hypotheses": [
                {
                    "statement": "checkout-api failed due to connection pool exhaustion",
                    "confidence": 0.8,
                    "citations": [citation],
                }
            ],
            "runbook_steps": [],
            "citations": [citation],
        }

    def judgment_args() -> dict[str, Any]:
        return {"score": 0.9, "is_grounded": True, "issues": [], "suggested_refinements": []}

    model = _function_model(signal_fn=signal_args, draft_fn=draft_args, judgment_fn=judgment_args)
    router = LLMRouter([FakeModelProvider(model)])
    graph_store = PostgresGraphStore(db)

    brief = await incidents_service.generate_brief(db, graph_store, router, incident=incident)

    assert brief.llm_used is True
    assert len(brief.hypotheses) == 1
    citation = brief.hypotheses[0].citations[0]
    assert citation.postmortem_title == "checkout-api pool exhaustion"
    assert "ORA-12520" in citation.content
    assert citation.char_end > citation.char_start

    matched = brief.matched_postmortems
    assert matched
    assert matched[0].postmortem.id == postmortem_id
    assert matched[0].overall_score > 0


async def test_a_low_critic_score_produces_a_visible_retry_in_the_stream(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    await _create_service(client, token, workspace_id, "checkout-api")
    postmortem_id = await _ingest(
        client, db, token=token, workspace_id=workspace_id, raw_text=_PM_TEXT
    )
    chunk_id = await _one_chunk_id(db, postmortem_id)
    incident = await _create_incident(
        db, workspace_id=workspace_id, raw_text="checkout-api pool exhaustion errors"
    )

    judgment_calls = {"count": 0}

    def signal_args() -> dict[str, Any]:
        return {
            "symptoms": ["checkout errors"],
            "error_strings": ["ORA-12520"],
            "metrics": {},
            "candidate_service_names": ["checkout-api"],
            "time_window": None,
            "severity_guess": "sev2",
            "extraction_confidence": 0.9,
        }

    def draft_args() -> dict[str, Any]:
        citation = {"chunk_id": str(chunk_id), "postmortem_id": str(postmortem_id), "quote": None}
        return {
            "hypotheses": [
                {
                    "statement": "checkout-api failed due to connection pool exhaustion",
                    "confidence": 0.8,
                    "citations": [citation],
                }
            ],
            "runbook_steps": [],
            "citations": [citation],
        }

    def judgment_args() -> dict[str, Any]:
        judgment_calls["count"] += 1
        if judgment_calls["count"] == 1:
            return {
                "score": 0.3,
                "is_grounded": False,
                "issues": ["thin evidence"],
                "suggested_refinements": ["pool exhaustion"],
            }
        return {"score": 0.9, "is_grounded": True, "issues": [], "suggested_refinements": []}

    model = _function_model(signal_fn=signal_args, draft_fn=draft_args, judgment_fn=judgment_args)
    router = LLMRouter([FakeModelProvider(model)])
    graph_store = PostgresGraphStore(db)

    events = [
        event
        async for event in incidents_service.stream_brief_generation(
            db, graph_store, router, incident=incident
        )
    ]

    event_types = [e["type"] for e in events]
    assert "retry" in event_types
    assert event_types[-1] == "done"
    assert events[-1]["brief_id"] is not None


async def test_generate_brief_degrades_cleanly_with_no_llm_available(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident = await _create_incident(db, workspace_id=workspace_id, raw_text="a bare alert")

    router = LLMRouter([])
    graph_store = PostgresGraphStore(db)

    brief = await incidents_service.generate_brief(db, graph_store, router, incident=incident)

    assert brief.llm_used is False
    assert brief.hypotheses == []
    assert brief.correction_passes == 0
