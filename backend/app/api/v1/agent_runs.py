import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentWorkspaceMember, DbSession
from app.core.pagination import CursorPage
from app.schemas.agent_run import AgentRunDetailOut, AgentRunOut, AgentRunStatsOut
from app.services import agent_run_service

router = APIRouter(prefix="/workspaces/{workspace_id}/agent-runs", tags=["agent-runs"])


@router.get("", response_model=CursorPage[AgentRunOut])
async def list_agent_runs(
    workspace_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = agent_run_service.DEFAULT_LIST_LIMIT,
) -> CursorPage[AgentRunOut]:
    items, next_cursor = await agent_run_service.list_runs(
        db, workspace_id=workspace_id, cursor=cursor, limit=limit
    )
    return CursorPage[AgentRunOut](items=items, next_cursor=next_cursor)


@router.get("/stats", response_model=AgentRunStatsOut)
async def get_agent_run_stats(
    workspace_id: uuid.UUID, membership: CurrentWorkspaceMember, db: DbSession
) -> AgentRunStatsOut:
    return await agent_run_service.get_stats(db, workspace_id=workspace_id)


@router.get("/{run_id}", response_model=AgentRunDetailOut)
async def get_agent_run(
    workspace_id: uuid.UUID, run_id: uuid.UUID, membership: CurrentWorkspaceMember, db: DbSession
) -> AgentRunDetailOut:
    return await agent_run_service.get_run_detail(db, workspace_id=workspace_id, run_id=run_id)
