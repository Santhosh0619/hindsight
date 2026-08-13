import uuid

import pytest
from httpx import AsyncClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import LLMUnavailableError
from app.models.postmortem import (
    FailureMode,
    PostmortemFact,
    PostmortemFailureMode,
    PostmortemService,
)
from app.services.extraction_service import run_extraction
from app.services.llm.router import LLMRouter
from app.workers import queue
from app.workers.handlers.extract_postmortem import handle_extract_postmortem
from app.workers.handlers.ingest_postmortem import handle_ingest_postmortem
from tests.conftest import FakeModelProvider, auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    workspace_id: str = response.json()["memberships"][0]["workspace_id"]
    return workspace_id


async def _create_and_ingest_postmortem(
    client: AsyncClient, db: AsyncSession, *, token: str, workspace_id: str, raw_text: str
) -> str:
    create_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/postmortems",
        json={"title": "pm", "raw_text": raw_text},
        headers=auth_headers(token),
    )
    postmortem_id: str = create_response.json()["id"]

    # Drain every currently-queued ingest job (not just "claim one and assume it's
    # ours") -- a leftover job from an earlier debug run sharing this dev database
    # would otherwise silently hijack a bare claim(..., limit=1), since claim() is
    # deliberately workspace-agnostic (a real worker pool spans every tenant).
    jobs = await queue.claim(db, worker_id="test-worker", kinds=["ingest_postmortem"], limit=50)
    for job in jobs:
        await handle_ingest_postmortem(db, job)
        await queue.complete(db, job=job)

    # Ingestion auto-enqueues an extract_postmortem job as a side effect. Most callers
    # here test extraction via run_extraction() directly and never touch the queue, so
    # that auto-enqueued job would otherwise sit as a permanent orphan -- draining and
    # discarding it keeps this file from leaking jobs that a later, unrelated test
    # (matching on kind + payload) could otherwise pick up by accident.
    extract_jobs = await queue.claim(
        db, worker_id="test-worker", kinds=["extract_postmortem"], limit=50
    )
    for job in extract_jobs:
        await queue.complete(db, job=job)

    return postmortem_id


def _fake_multi_agent_function(*, real_chunk_id: uuid.UUID, real_service_name: str):  # type: ignore[no-untyped-def]
    fake_chunk_id = uuid.uuid4()

    def respond(messages: list[object], info: AgentInfo) -> ModelResponse:
        schema_title = info.output_tools[0].parameters_json_schema.get("title")
        tool_name = info.output_tools[0].name
        if schema_title == "ExtractedFacts":
            args = {
                "triggers": [],
                "root_causes": [
                    {"statement": "real fact", "chunk_id": str(real_chunk_id), "confidence": 0.9},
                    {
                        "statement": "hallucinated fact",
                        "chunk_id": str(fake_chunk_id),
                        "confidence": 0.9,
                    },
                ],
                "remediations": [],
                "detection_gaps": [],
                "contributing_factors": [],
            }
        elif schema_title == "FailureModeClassificationResult":
            args = {"classifications": [{"family": "configuration_error", "confidence": 0.8}]}
        elif schema_title == "ServiceLinkResult":
            args = {
                "links": [
                    {"service_name": real_service_name, "role": "root_cause", "confidence": 0.9},
                    {
                        "service_name": "nonexistent-service",
                        "role": "affected",
                        "confidence": 0.5,
                    },
                ]
            }
        else:
            raise ValueError(f"unexpected output schema: {schema_title}")
        return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=args)])

    return respond


async def test_run_extraction_drops_hallucinated_facts_and_unresolved_services(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    service_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": "payments-svc", "tier": 1},
        headers=auth_headers(token),
    )
    assert service_response.status_code == 201, service_response.text

    postmortem_id = await _create_and_ingest_postmortem(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text="Summary:\npayments-svc misconfigured after a deploy.\n",
    )

    detail_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/postmortems/{postmortem_id}",
        headers=auth_headers(token),
    )
    real_chunk_id = uuid.UUID(detail_response.json()["chunks"][0]["id"])

    model = FunctionModel(
        _fake_multi_agent_function(real_chunk_id=real_chunk_id, real_service_name="payments-svc")
    )
    router = LLMRouter([FakeModelProvider(model)])

    summary = await run_extraction(db, router, postmortem_id=uuid.UUID(postmortem_id))

    assert summary.fact_count == 1
    assert summary.failure_mode_count == 1
    assert summary.service_link_count == 1

    facts = (
        (
            await db.execute(
                select(PostmortemFact).where(
                    PostmortemFact.postmortem_id == uuid.UUID(postmortem_id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(facts) == 1
    assert facts[0].source_chunk_id == real_chunk_id

    links = (
        (
            await db.execute(
                select(PostmortemService).where(
                    PostmortemService.postmortem_id == uuid.UUID(postmortem_id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(links) == 1

    failure_modes = (
        (
            await db.execute(
                select(PostmortemFailureMode).where(
                    PostmortemFailureMode.postmortem_id == uuid.UUID(postmortem_id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(failure_modes) == 1


async def test_failure_mode_get_or_create_does_not_duplicate_rows(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    pm1 = await _create_and_ingest_postmortem(
        client, db, token=token, workspace_id=workspace_id, raw_text="Summary:\nFirst incident.\n"
    )
    pm2 = await _create_and_ingest_postmortem(
        client, db, token=token, workspace_id=workspace_id, raw_text="Summary:\nSecond incident.\n"
    )

    for postmortem_id in (pm1, pm2):
        detail = await client.get(
            f"/api/v1/workspaces/{workspace_id}/postmortems/{postmortem_id}",
            headers=auth_headers(token),
        )
        chunk_id = uuid.UUID(detail.json()["chunks"][0]["id"])
        model = FunctionModel(
            _fake_multi_agent_function(real_chunk_id=chunk_id, real_service_name="none")
        )
        router = LLMRouter([FakeModelProvider(model)])
        await run_extraction(db, router, postmortem_id=uuid.UUID(postmortem_id))

    rows = (
        (
            await db.execute(
                select(FailureMode).where(
                    FailureMode.workspace_id == uuid.UUID(workspace_id),
                    FailureMode.label == "configuration_error",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_run_extraction_on_deleted_postmortem_is_a_no_op(db: AsyncSession) -> None:
    router = LLMRouter([])
    summary = await run_extraction(db, router, postmortem_id=uuid.uuid4())
    assert summary.fact_count == 0
    assert summary.failure_mode_count == 0
    assert summary.service_link_count == 0


async def test_handle_extract_postmortem_fails_cleanly_with_no_llm_configured(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Uses the real build_router(get_settings()) -- no mocking -- against this build's
    # actual configuration (no Gemini/Groq key, no local Ollama server running), per
    # FR-09: the job must fail with a readable error, not hang or crash the worker.
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    postmortem_id = await _create_and_ingest_postmortem(
        client, db, token=token, workspace_id=workspace_id, raw_text="Summary:\nSomething broke.\n"
    )

    # Enqueue a dedicated job for this test rather than relying on the one ingestion
    # auto-enqueues (the helper above already drains and discards that one) -- avoids
    # any ambiguity about which queued extract_postmortem job belongs to this test.
    job = await queue.enqueue(
        db,
        workspace_id=uuid.UUID(workspace_id),
        kind="extract_postmortem",
        payload={"postmortem_id": postmortem_id},
    )

    with pytest.raises(LLMUnavailableError):
        await handle_extract_postmortem(db, job)
