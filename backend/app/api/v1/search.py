import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.core.deps import CurrentWorkspaceMember, DbSession
from app.schemas.search import SearchMode, SearchResponseOut
from app.services.postgres_graph_store import PostgresGraphStore
from app.services.retrieval.hybrid import hybrid_search

router = APIRouter(prefix="/workspaces/{workspace_id}/search", tags=["search"])


@router.get("", response_model=SearchResponseOut)
async def search(
    workspace_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
    q: Annotated[str, Query(min_length=1)],
    mode: Annotated[SearchMode, Query()] = "hybrid",
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> SearchResponseOut:
    top_k = limit if limit is not None else get_settings().retrieval_top_k
    graph_store = PostgresGraphStore(db)
    return await hybrid_search(
        db, graph_store, workspace_id=workspace_id, query=q, mode=mode, top_k=top_k
    )
