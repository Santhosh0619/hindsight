import uuid
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.build_graph import build_graph
from app.agents.state import initial_state
from app.agents.streaming import stream_graph_events
from app.models.agent import AgentRun, AgentRunStep
from app.models.incident import Incident
from app.services.llm.router import LLMRouter
from app.services.postgres_graph_store import PostgresGraphStore
from tests.conftest import FakeModelProvider, auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return uuid.UUID(response.json()["memberships"][0]["workspace_id"])


async def _create_incident(
    db: AsyncSession, *, workspace_id: uuid.UUID, raw_text: str
) -> uuid.UUID:
    incident = Incident(
        workspace_id=workspace_id,
        title="streaming test incident",
        raw_alert_text=raw_text,
        opened_at=datetime.now(UTC),
    )
    db.add(incident)
    await db.commit()
    return incident.id


async def _create_agent_run(db: AsyncSession, *, incident_id: uuid.UUID) -> uuid.UUID:
    run = AgentRun(
        incident_id=incident_id,
        graph_version="test",
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.commit()
    return run.id


def _judgment_fn_factory(calls: dict[str, int]) -> Any:
    def judgment_fn() -> dict[str, Any]:
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "score": 0.2,
                "is_grounded": False,
                "issues": ["needs more evidence"],
                "suggested_refinements": ["more detail"],
            }
        return {"score": 1.0, "is_grounded": True, "issues": [], "suggested_refinements": []}

    return judgment_fn


def _function_model(*, judgment_fn: Any) -> FunctionModel:
    def fn(_messages: list[Any], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        props = set(tool.parameters_json_schema.get("properties", {}).keys())
        if "candidate_service_names" in props:
            args: dict[str, Any] = {
                "symptoms": [],
                "error_strings": [],
                "metrics": {},
                "candidate_service_names": [],
                "time_window": None,
                "severity_guess": None,
                "extraction_confidence": None,
            }
        elif "hypotheses" in props:
            args = {"hypotheses": [], "runbook_steps": [], "citations": []}
        elif "is_grounded" in props:
            args = judgment_fn()
        else:
            raise AssertionError(f"unexpected output schema: {sorted(props)}")
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])

    return FunctionModel(fn)


async def test_stream_graph_events_emits_node_lifecycle_and_a_retry_and_writes_steps(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(db, workspace_id=workspace_id, raw_text="a bare alert")
    run_id = await _create_agent_run(db, incident_id=incident_id)

    judgment_calls = {"count": 0}
    model = _function_model(judgment_fn=_judgment_fn_factory(judgment_calls))
    router = LLMRouter([FakeModelProvider(model)])
    graph_store = PostgresGraphStore(db)
    graph = build_graph(db, graph_store, router)

    state = initial_state(
        incident_id=incident_id, workspace_id=workspace_id, raw_text="a bare alert"
    )
    events = [
        event
        async for event in stream_graph_events(
            graph, state, thread_id=str(incident_id), run_id=run_id
        )
    ]

    event_types = [e["type"] for e in events]
    assert "retry" in event_types  # the forced low first-pass score triggers one retry
    assert event_types[-1] == "done"
    assert events[-1]["brief_id"] is not None

    node_starts = [e["node"] for e in events if e["type"] == "node_start"]
    node_ends = [e["node"] for e in events if e["type"] == "node_end"]
    assert node_starts.count("retriever") == 2  # ran once initially, once on retry
    assert node_starts == node_ends  # every start has a matching end, in the same order
    assert node_starts[-1] == "briefer"

    persisted_steps = await db.execute(
        select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.seq)
    )
    steps = list(persisted_steps.scalars().all())
    assert len(steps) == len(node_ends)
    assert [s.node_name for s in steps] == node_ends
    assert all(s.status == "done" for s in steps)
    assert all(s.latency_ms is not None for s in steps)
