import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EvalRunMode = Literal["vector", "vector_bm25", "full"]


class EvalRunOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    mode: EvalRunMode | None
    started_at: datetime
    finished_at: datetime | None
    recall_at_1: float | None
    recall_at_5: float | None
    mrr: float | None
    groundedness: float | None
    citation_validity: float | None
    cases_run: int


class EvalCaseResultOut(BaseModel):
    id: uuid.UUID
    eval_case_id: uuid.UUID
    case_name: str
    retrieved_ids: list[uuid.UUID]
    rank_of_first_hit: int | None
    groundedness: float | None
    passed: bool


class EvalRunDetailOut(EvalRunOut):
    results: list[EvalCaseResultOut]
