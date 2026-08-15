import uuid
from datetime import datetime

from pydantic import BaseModel


class AgentRunOut(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    incident_title: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    total_tokens_in: int
    total_tokens_out: int
    from_cache: bool


class AgentRunStepOut(BaseModel):
    id: uuid.UUID
    seq: int
    node_name: str
    status: str
    latency_ms: int | None
    tokens_in: int
    tokens_out: int
    output_summary: dict[str, object]
    error: str | None


class AgentRunDetailOut(AgentRunOut):
    steps: list[AgentRunStepOut]


class AgentRunStatsOut(BaseModel):
    total_runs: int
    total_tokens_in: int
    total_tokens_out: int
    cache_hit_rate: float | None
