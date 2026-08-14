import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.catalog import ServiceOut


class IngestHealthOut(BaseModel):
    indexed: int
    processing: int
    pending: int
    failed: int


class MttrPointOut(BaseModel):
    week_start: date
    mttr_minutes: float | None


class FragileServiceOut(BaseModel):
    service: ServiceOut
    incident_count: int
    blast_radius_size: int
    fragility_score: float


class RecentBriefOut(BaseModel):
    incident_id: uuid.UUID
    incident_title: str
    brief_id: uuid.UUID
    version: int
    overall_confidence: float | None
    generated_at: datetime | None


class DashboardOut(BaseModel):
    open_incidents: int
    briefs_generated: int
    corpus_size: int
    ingest_health: IngestHealthOut
    mttr_trend: list[MttrPointOut]
    fragile_services: list[FragileServiceOut]
    recent_briefs: list[RecentBriefOut]
