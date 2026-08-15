import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.evaluation import EvalCase, EvalCaseResult, EvalRun
from app.schemas.evaluation import EvalCaseResultOut, EvalRunDetailOut, EvalRunOut

DEFAULT_RUNS_LIMIT = 20


async def list_runs(
    db: AsyncSession, *, workspace_id: uuid.UUID, limit: int = DEFAULT_RUNS_LIMIT
) -> list[EvalRunOut]:
    result = await db.execute(
        select(EvalRun)
        .where(EvalRun.workspace_id == workspace_id)
        .order_by(EvalRun.started_at.desc())
        .limit(limit)
    )
    return [EvalRunOut.model_validate(run) for run in result.scalars().all()]


async def get_run_detail(
    db: AsyncSession, *, workspace_id: uuid.UUID, run_id: uuid.UUID
) -> EvalRunDetailOut:
    run_result = await db.execute(
        select(EvalRun).where(EvalRun.id == run_id, EvalRun.workspace_id == workspace_id)
    )
    run = run_result.scalar_one_or_none()
    if run is None:
        raise NotFoundError("Eval run not found")

    results_result = await db.execute(
        select(EvalCaseResult, EvalCase.name)
        .join(EvalCase, EvalCase.id == EvalCaseResult.eval_case_id)
        .where(EvalCaseResult.eval_run_id == run_id)
    )
    results = [
        EvalCaseResultOut(
            id=result.id,
            eval_case_id=result.eval_case_id,
            case_name=case_name,
            retrieved_ids=result.retrieved_ids,
            rank_of_first_hit=result.rank_of_first_hit,
            groundedness=result.groundedness,
            passed=result.passed,
        )
        for result, case_name in results_result.all()
    ]

    return EvalRunDetailOut(**EvalRunOut.model_validate(run).model_dump(), results=results)
