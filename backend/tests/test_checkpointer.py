import uuid
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.build_graph import build_graph, checkpointer_conn_string
from app.agents.state import initial_state
from app.core.config import get_settings
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
        title="checkpoint test incident",
        raw_alert_text=raw_text,
        opened_at=datetime.now(UTC),
    )
    db.add(incident)
    await db.commit()
    return incident.id


def _flat_model() -> FunctionModel:
    # No candidate services, no citations needed -- this test only cares whether the
    # checkpointer persisted a run, not about draft quality.
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
            args = {"score": 1.0, "is_grounded": True, "issues": [], "suggested_refinements": []}
        else:
            raise AssertionError(f"unexpected output schema: {sorted(props)}")
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])

    return FunctionModel(fn)


async def test_a_graph_run_is_actually_persisted_to_the_postgres_checkpointer(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    incident_id = await _create_incident(
        db, workspace_id=workspace_id, raw_text="a bare alert with no known services"
    )

    router = LLMRouter([FakeModelProvider(_flat_model())])
    graph_store = PostgresGraphStore(db)

    conn_string = checkpointer_conn_string(get_settings())
    async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
        await saver.setup()
        graph = build_graph(db, graph_store, router, checkpointer=saver)

        thread_id = str(incident_id)
        config = {"configurable": {"thread_id": thread_id}}
        state = initial_state(
            incident_id=incident_id, workspace_id=workspace_id, raw_text="a bare alert"
        )
        final_state = await graph.ainvoke(state, config=config)
        assert final_state["final"] is not None

        checkpoint_tuple = await saver.aget_tuple(config)
        assert checkpoint_tuple is not None
        persisted_values = checkpoint_tuple.checkpoint["channel_values"]
        assert persisted_values["incident_id"] == incident_id
        assert persisted_values["retry_count"] == 0

        # A second read against the same thread_id resumes the same run's state --
        # this is the "agent memory" story FR-09 exists for.
        resumed = await saver.aget(config)
        assert resumed is not None
