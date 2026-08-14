import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postmortem import PostmortemService, ServiceLinkRole
from app.services.ingestion.embed import embed
from app.services.postgres_graph_store import PostgresGraphStore
from app.services.retrieval.graph import search_graph
from app.services.retrieval.keyword import search_keyword
from app.services.retrieval.vector import search_vector
from app.workers import queue
from app.workers.handlers.ingest_postmortem import handle_ingest_postmortem
from tests.conftest import auth_headers, signup


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

    # Ingestion auto-enqueues an extract_postmortem job (Phase 6); this file tests
    # retrieval directly against manually-seeded postmortem_services rows, not real
    # extraction -- drain and discard so it doesn't leak into another test file.
    extract_jobs = await queue.claim(
        db, worker_id="test-worker", kinds=["extract_postmortem"], limit=50
    )
    for job in extract_jobs:
        await queue.complete(db, job=job)

    return postmortem_id


async def test_vector_search_finds_a_paraphrase_with_no_shared_vocabulary(
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
            "during peak traffic.\n"
        ),
    )

    [query_embedding] = await embed(["The connection pool was exhausted."])
    hits = await search_vector(
        db, workspace_id=workspace_id, query_embedding=query_embedding, top_k=5
    )

    assert target_id in {hit.postmortem_id for hit in hits}


async def test_keyword_search_finds_an_exact_error_code(
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
            "Summary:\nORA-12520: TNS listener could not find available handler for connection.\n"
        ),
    )
    await _ingest(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text="Summary:\nA completely unrelated database configuration issue occurred.\n",
    )

    # websearch_to_tsquery's @@ filter is a hard match, not a similarity score -- only
    # the postmortem containing the literal code passes it at all, so this is a
    # precise positive test of exact-string matching, not a comparative ranking claim
    # about how vector search would have done on the same query.
    hits = await search_keyword(db, workspace_id=workspace_id, query="ORA-12520", top_k=5)

    assert len(hits) == 1
    assert hits[0].postmortem_id == target_id


async def test_graph_search_finds_a_postmortem_linked_to_a_neighbor_service(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)
    workspace_id_str = str(workspace_id)

    checkout_response = await client.post(
        f"/api/v1/workspaces/{workspace_id_str}/catalog/services",
        json={"name": "checkout-api", "tier": 1},
        headers=auth_headers(token),
    )
    payments_response = await client.post(
        f"/api/v1/workspaces/{workspace_id_str}/catalog/services",
        json={"name": "payments-svc", "tier": 1},
        headers=auth_headers(token),
    )
    checkout_id = uuid.UUID(checkout_response.json()["id"])
    payments_id = uuid.UUID(payments_response.json()["id"])

    edge_response = await client.post(
        f"/api/v1/workspaces/{workspace_id_str}/catalog/edges",
        json={
            "from_service_id": str(checkout_id),
            "to_service_id": str(payments_id),
            "kind": "calls",
            "criticality": "hard",
        },
        headers=auth_headers(token),
    )
    assert edge_response.status_code == 201, edge_response.text

    # Never mentions "checkout-api" -- only reachable via checkout-api's neighborhood.
    target_id = await _ingest(
        client,
        db,
        token=token,
        workspace_id=workspace_id,
        raw_text="Summary:\npayments-svc rejected transactions after a bad deploy.\n",
    )
    db.add(
        PostmortemService(
            postmortem_id=target_id,
            service_id=payments_id,
            role=ServiceLinkRole.ROOT_CAUSE,
        )
    )
    await db.commit()

    graph_store = PostgresGraphStore(db)
    hits = await search_graph(
        db, graph_store, workspace_id=workspace_id, query="checkout-api", top_k=5
    )

    assert len(hits) == 1
    assert hits[0].postmortem_id == target_id
    assert hits[0].matched_service_name == "checkout-api"
    assert hits[0].via_service_name == "payments-svc"


async def test_graph_search_returns_empty_when_query_matches_no_service(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    workspace_id = await _workspace_id(client, token)

    graph_store = PostgresGraphStore(db)
    hits = await search_graph(
        db, graph_store, workspace_id=workspace_id, query="nothing matches this", top_k=5
    )

    assert hits == []
