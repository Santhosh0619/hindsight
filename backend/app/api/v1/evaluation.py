import uuid

from fastapi import APIRouter, Query

from app.core.deps import CurrentWorkspaceMember, DbSession
from app.schemas.evaluation import EvalRunDetailOut, EvalRunOut
from app.services import evaluation_service

router = APIRouter(prefix="/workspaces/{workspace_id}/evaluation", tags=["evaluation"])


@router.get("/runs", response_model=list[EvalRunOut])
async def list_eval_runs(
    workspace_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
    limit: int = Query(default=evaluation_service.DEFAULT_RUNS_LIMIT, ge=1, le=100),
) -> list[EvalRunOut]:
    return await evaluation_service.list_runs(db, workspace_id=workspace_id, limit=limit)


@router.get("/runs/{run_id}", response_model=EvalRunDetailOut)
async def get_eval_run(
    workspace_id: uuid.UUID, run_id: uuid.UUID, membership: CurrentWorkspaceMember, db: DbSession
) -> EvalRunDetailOut:
    return await evaluation_service.get_run_detail(db, workspace_id=workspace_id, run_id=run_id)
