import uuid

import pytest
from httpx import AsyncClient
from pydantic_ai.models.test import TestModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.models.evaluation import EvalCase, EvalCaseResult
from app.models.postmortem import FactType, PostmortemChunk, PostmortemFact
from app.services.evaluation.runner import run_eval
from app.services.llm.router import LLMRouter
from app.services.postgres_graph_store import PostgresGraphStore
from app.workers import queue
from app.workers.handlers.ingest_postmortem import handle_ingest_postmortem
from tests.conftest import FakeModelProvider, auth_headers, signup

_NO_LLM_ROUTER = LLMRouter([])  # no providers -> LLMUnavailableError on every call


async def _workspace_id(client: AsyncClient, token: str) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return uuid.UUID(response.json()["memberships"][0]["workspace_id"])


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

    # Drain and discard the auto-chained extract_postmortem job -- this file exercises
    # eval directly against manually-added facts, not real LLM extraction.
    extract_jobs = await queue.claim(
        db, worker_id="test-worker", kinds=["extract_postmortem"], limit=50
    )
    for job in extract_jobs:
        await queue.complete(db, job=job)

    return postmortem_id


async def _add_root_cause_fact(
    db: AsyncSession, *, postmortem_id: uuid.UUID, statement: str
) -> None:
    chunk_result = await db.execute(
        select(PostmortemChunk)
        .where(PostmortemChunk.postmortem_id == postmortem_id)
        .order_by(PostmortemChunk.chunk_index)
        .limit(1)
    )
    chunk = chunk_result.scalars().first()
    assert chunk is not None
    db.add(
        PostmortemFact(
            postmortem_id=postmortem_id,
            fact_type=FactType.ROOT_CAUSE,
            statement=statement,
            confidence=0.9,
            source_chunk_id=chunk.id,
        )
    )
    await db.commit()


async def test_run_eval_scores_recall_and_mrr_against_real_retrieval(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    target_id = await _ingest(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text=(
            "Summary:\nOur database ran completely out of available connections "
            "during peak checkout traffic.\n"
        ),
    )
    await _ingest(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text="Summary:\nA completely unrelated DNS misconfiguration caused an outage.\n",
    )
    await _add_root_cause_fact(
        db,
        postmortem_id=target_id,
        statement="The database ran out of available connections during checkout traffic.",
    )

    db.add(
        EvalCase(
            workspace_id=workspace_id,
            name="pool-exhaustion",
            incident_text="The connection pool was exhausted under load.",
            expected_postmortem_ids=[target_id],
            expected_service_ids=[],
        )
    )
    await db.commit()

    graph_store = PostgresGraphStore(db)
    run = await run_eval(
        db,
        graph_store,
        _NO_LLM_ROUTER,
        workspace_id=workspace_id,
        mode="vector",
        top_k=5,
        llm_configured=False,
    )

    assert run.cases_run == 1
    assert run.recall_at_1 == 1.0
    assert run.recall_at_5 == 1.0
    assert run.mrr == 1.0
    assert run.citation_validity == 1.0
    assert run.groundedness is None  # no LLM key -> gracefully skipped
    assert run.mode == "vector"

    results = (
        (await db.execute(select(EvalCaseResult).where(EvalCaseResult.eval_run_id == run.id)))
        .scalars()
        .all()
    )
    assert len(results) == 1
    assert results[0].rank_of_first_hit == 1
    assert results[0].passed is True


async def test_run_eval_misses_when_expected_postmortem_never_retrieved(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    await _ingest(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text="Summary:\nAn unrelated certificate expiry took down the auth service.\n",
    )

    never_indexed_id = uuid.uuid4()
    db.add(
        EvalCase(
            workspace_id=workspace_id,
            name="never-matches",
            incident_text="Completely unrelated query about disk saturation.",
            expected_postmortem_ids=[never_indexed_id],
            expected_service_ids=[],
        )
    )
    await db.commit()

    graph_store = PostgresGraphStore(db)
    run = await run_eval(
        db,
        graph_store,
        _NO_LLM_ROUTER,
        workspace_id=workspace_id,
        mode="vector",
        top_k=5,
        llm_configured=False,
    )

    assert run.recall_at_1 == 0.0
    assert run.recall_at_5 == 0.0
    assert run.mrr == 0.0

    results = (
        (await db.execute(select(EvalCaseResult).where(EvalCaseResult.eval_run_id == run.id)))
        .scalars()
        .all()
    )
    assert results[0].rank_of_first_hit is None
    assert results[0].passed is False


async def test_run_eval_computes_groundedness_when_llm_configured(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    target_id = await _ingest(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text="Summary:\nA retry storm overwhelmed the payments service.\n",
    )
    await _add_root_cause_fact(
        db, postmortem_id=target_id, statement="A retry storm overwhelmed the service."
    )
    db.add(
        EvalCase(
            workspace_id=workspace_id,
            name="retry-storm",
            incident_text="A retry storm is overwhelming the payments service.",
            expected_postmortem_ids=[target_id],
            expected_service_ids=[],
        )
    )
    await db.commit()

    model = TestModel(
        custom_output_args={
            "score": 0.85,
            "is_grounded": True,
            "issues": [],
            "suggested_refinements": [],
        }
    )
    router = LLMRouter([FakeModelProvider(model)])
    graph_store = PostgresGraphStore(db)

    run = await run_eval(
        db,
        graph_store,
        router,
        workspace_id=workspace_id,
        mode="vector",
        top_k=5,
        llm_configured=True,
    )

    assert run.groundedness == 0.85


async def test_run_eval_raises_when_workspace_has_no_eval_cases(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    graph_store = PostgresGraphStore(db)

    with pytest.raises(ValidationAppError):
        await run_eval(
            db,
            graph_store,
            _NO_LLM_ROUTER,
            workspace_id=workspace_id,
            mode="vector",
            top_k=5,
            llm_configured=False,
        )
