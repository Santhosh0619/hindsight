import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.incident import FeedbackVerdict, IncidentStatus
from app.models.postmortem import Severity
from app.schemas.postmortem import PostmortemOut
from app.services.graph_store import BlastRadius


class IncidentCreate(BaseModel):
    title: str
    raw_alert_text: str
    external_ref: str | None = None
    severity: Severity | None = None


class IncidentUpdate(BaseModel):
    status: IncidentStatus | None = None
    title: str | None = None


class IncidentOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    external_ref: str | None
    title: str
    raw_alert_text: str
    severity: str | None
    status: IncidentStatus
    opened_by: uuid.UUID | None
    opened_at: datetime
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CitationOut(BaseModel):
    chunk_id: uuid.UUID
    postmortem_id: uuid.UUID
    postmortem_title: str
    quote: str | None
    content: str
    char_start: int
    char_end: int


class HypothesisOut(BaseModel):
    statement: str
    confidence: float
    citations: list[CitationOut]


class RunbookStepOut(BaseModel):
    step: str
    source_postmortem_id: uuid.UUID | None
    citation: CitationOut | None


class MatchedPostmortemOut(BaseModel):
    postmortem: PostmortemOut
    vector_score: float
    keyword_score: float
    graph_score: float
    failure_mode_overlap: float
    recency: float
    overall_score: float
    rank: int


class BriefOut(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    version: int
    hypotheses: list[HypothesisOut]
    matched_postmortems: list[MatchedPostmortemOut]
    blast_radius: BlastRadius
    runbook_steps: list[RunbookStepOut]
    citations: list[CitationOut]
    overall_confidence: float | None
    correction_passes: int
    llm_used: bool
    from_cache: bool
    generated_at: datetime | None


class BriefFeedbackCreate(BaseModel):
    verdict: FeedbackVerdict
    correct_postmortem_id: uuid.UUID | None = None
    note: str | None = None


class BriefFeedbackOut(BaseModel):
    id: uuid.UUID
    brief_id: uuid.UUID
    user_id: uuid.UUID | None
    verdict: FeedbackVerdict
    correct_postmortem_id: uuid.UUID | None
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
