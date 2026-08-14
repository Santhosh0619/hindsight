import uuid
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.build_graph import build_graph
from app.agents.nodes import normalizer_node
from app.agents.state import initial_state
from app.models.incident import Brief, Incident
from app.models.incident import IncidentSignal as IncidentSignalRow
from app.models.postmortem import PostmortemChunk
from app.services.llm.router import LLMRouter
from app.services.postgres_graph_store import PostgresGraphStore
from app.workers import queue
from app.workers.handlers.ingest_postmortem import handle_ingest_postmortem
from tests.conftest import FakeModelProvider, auth_headers, signup

_RAW_ALERT = "checkout-api is throwing ORA-12520 connection pool exhaustion errors"
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
        json={"title": "pm", "raw_text": raw_text},
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


async def _create_incident(
    db: AsyncSession, *, workspace_id: uuid.UUID, raw_text: str
) -> uuid.UUID:
    # No /incidents API exists yet (Phase 9) -- this phase's own graph tests seed the
    # row directly, exactly the boundary the PRD's Out of Scope draws.
    incident = Incident(
        workspace_id=workspace_id,
        title="test incident",
        raw_alert_text=raw_text,
        opened_at=datetime.now(UTC),
    )
    db.add(incident)
    await db.commit()
    return incident.id


async def _one_chunk_id(db: AsyncSession, postmortem_id: uuid.UUID) -> uuid.UUID:
    result = await db.execute(
        select(PostmortemChunk.id).where(PostmortemChunk.postmortem_id == postmortem_id)
    )
    return result.scalars().first()


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


async def test_full_graph_fires_all_six_nodes_in_order_and_persists_a_typed_brief(
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
    graph = build_graph(db, graph_store, router)

    incident_id = await _create_incident(db, workspace_id=workspace_id, raw_text=_RAW_ALERT)
    state = initial_state(incident_id=incident_id, workspace_id=workspace_id, raw_text=_RAW_ALERT)
    final_state = await graph.ainvoke(state)

    fired_nodes = [
        entry["node"] if isinstance(entry, dict) else entry.node for entry in final_state["trace"]
    ]
    assert fired_nodes == ["normalizer", "retriever", "correlator", "analyst", "critic", "briefer"]

    brief = final_state["final"]
    assert brief.incident_id == incident_id
    assert brief.llm_used is True
    assert brief.correction_passes == 0
    assert len(brief.hypotheses) == 1
    assert brief.matched_postmortems  # correlator produced at least one CandidateMatch

    persisted = await db.execute(select(Brief).where(Brief.incident_id == incident_id))
    assert persisted.scalars().first() is not None
    signal_row = await db.execute(
        select(IncidentSignalRow).where(IncidentSignalRow.incident_id == incident_id)
    )
    assert signal_row.scalars().first() is not None


async def test_a_low_critic_score_triggers_exactly_one_retry(
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
    graph = build_graph(db, graph_store, router)

    incident_id = await _create_incident(db, workspace_id=workspace_id, raw_text=_RAW_ALERT)
    state = initial_state(incident_id=incident_id, workspace_id=workspace_id, raw_text=_RAW_ALERT)
    final_state = await graph.ainvoke(state)

    assert judgment_calls["count"] == 2  # exactly one retry -> critic ran twice
    assert final_state["retry_count"] == 1
    assert final_state["final"].correction_passes == 1

    retriever_runs = [
        e
        for e in final_state["trace"]
        if (e["node"] if isinstance(e, dict) else e.node) == "retriever"
    ]
    assert len(retriever_runs) == 2
    # AC-3: the retry's query differs from the original -- suggested_refinements got
    # folded in, verifiable via the retry's own hybrid_search call (surfaced in trace).
    first_note = (
        retriever_runs[0]["note"] if isinstance(retriever_runs[0], dict) else retriever_runs[0].note
    )
    second_note = (
        retriever_runs[1]["note"] if isinstance(retriever_runs[1], dict) else retriever_runs[1].note
    )
    assert first_note != second_note
    assert "pool exhaustion" in second_note


async def test_graph_completes_with_deterministic_content_when_no_llm_is_available(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    await _create_service(client, token, workspace_id, "checkout-api")
    await _ingest(client, db, token=token, workspace_id=workspace_id, raw_text=_PM_TEXT)

    router = LLMRouter([])  # no providers at all -> LLMUnavailableError on every call
    graph_store = PostgresGraphStore(db)
    graph = build_graph(db, graph_store, router)

    incident_id = await _create_incident(db, workspace_id=workspace_id, raw_text=_RAW_ALERT)
    state = initial_state(incident_id=incident_id, workspace_id=workspace_id, raw_text=_RAW_ALERT)
    final_state = await graph.ainvoke(state)

    brief = final_state["final"]
    assert brief.llm_used is False
    assert brief.hypotheses == []
    assert brief.correction_passes == 0  # never retried -- nothing to gain
    # The deterministic correlator still ran against real retrieval (raw_text fallback
    # query, since normalizer had no LLM to extract symptoms/error strings with).
    assert brief.matched_postmortems


async def test_normalizer_resolves_known_services_and_flags_unresolved_mentions(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    await _create_service(client, token, workspace_id, "checkout-api")

    def signal_args() -> dict[str, Any]:
        return {
            "symptoms": ["checkout errors"],
            "error_strings": [],
            "metrics": {},
            "candidate_service_names": ["checkout-api", "totally-made-up-service"],
            "time_window": None,
            "severity_guess": "sev2",
            "extraction_confidence": 0.9,
        }

    model = _function_model(
        signal_fn=signal_args,
        draft_fn=lambda: {"hypotheses": [], "runbook_steps": [], "citations": []},
        judgment_fn=lambda: {
            "score": 1.0,
            "is_grounded": True,
            "issues": [],
            "suggested_refinements": [],
        },
    )
    router = LLMRouter([FakeModelProvider(model)])

    incident_id = await _create_incident(db, workspace_id=workspace_id, raw_text=_RAW_ALERT)
    state = initial_state(incident_id=incident_id, workspace_id=workspace_id, raw_text=_RAW_ALERT)

    update = await normalizer_node(state, db=db, router=router)
    signal = update["signal"]

    assert len(signal.affected_service_ids) == 1  # only checkout-api resolves
    assert signal.unresolved_mentions == ["totally-made-up-service"]
