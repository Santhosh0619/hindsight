import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.postmortem import Severity
from app.services.graph_store import BlastRadius


class TimeWindowOut(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    description: str | None = None


class IncidentSignalOut(BaseModel):
    """Raw pydantic-ai agent output -- candidate_service_names are unresolved names,
    not ids. Named *Out (not IncidentSignal) to avoid colliding with the Phase 1 DB
    model of the same name."""

    symptoms: list[str]
    error_strings: list[str]
    metrics: dict[str, float]
    candidate_service_names: list[str]
    time_window: TimeWindowOut | None = None
    severity_guess: Severity | None = None
    extraction_confidence: float | None = None


class NormalizedSignal(BaseModel):
    """IncidentSignalOut after normalizer_node resolves candidate_service_names
    against the real catalog."""

    symptoms: list[str]
    error_strings: list[str]
    metrics: dict[str, float]
    affected_service_ids: list[uuid.UUID]
    unresolved_mentions: list[str]
    time_window: TimeWindowOut | None = None
    severity_guess: Severity | None = None
    extracted_by_model: str | None = None
    extraction_confidence: float | None = None


class CandidateMatch(BaseModel):
    postmortem_id: uuid.UUID
    vector_score: float
    keyword_score: float
    graph_score: float
    failure_mode_overlap: float
    recency: float
    overall_score: float
    rank: int


class Citation(BaseModel):
    chunk_id: uuid.UUID
    postmortem_id: uuid.UUID
    quote: str | None = None


class Hypothesis(BaseModel):
    statement: str
    confidence: float
    citations: list[Citation] = Field(min_length=1)


class RunbookStepDraft(BaseModel):
    step: str
    source_postmortem_id: uuid.UUID | None = None
    citation: Citation | None = None


class DraftBrief(BaseModel):
    hypotheses: list[Hypothesis]
    runbook_steps: list[RunbookStepDraft]
    citations: list[Citation]


class LLMVerificationJudgment(BaseModel):
    """The LLM judge's own output -- invalid_citations is never asked of the model,
    since that's the deterministic stage's job, not something an LLM should self-report."""

    score: float
    is_grounded: bool
    issues: list[str]
    suggested_refinements: list[str]


class VerificationResult(BaseModel):
    score: float
    is_grounded: bool
    issues: list[str]
    suggested_refinements: list[str]
    invalid_citations: list[Citation] = Field(default_factory=list)


class IncidentBrief(BaseModel):
    incident_id: uuid.UUID
    version: int
    hypotheses: list[Hypothesis]
    matched_postmortems: list[CandidateMatch]
    blast_radius: BlastRadius
    runbook_steps: list[RunbookStepDraft]
    citations: list[Citation]
    overall_confidence: float | None
    correction_passes: int
    llm_used: bool
    from_cache: bool
