import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.models.postmortem import FactType, PostmortemStatus, ServiceLinkRole, Severity
from app.schemas.catalog import ServiceOut

MAX_BULK_POSTMORTEMS = 20


class PostmortemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    raw_text: str = Field(min_length=1)
    external_ref: str | None = Field(default=None, max_length=200)
    occurred_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    severity: Severity | None = None

    @field_validator("raw_text")
    @classmethod
    def _raw_text_within_size_cap(cls, value: str) -> str:
        max_bytes = get_settings().max_upload_bytes
        if len(value.encode("utf-8")) > max_bytes:
            raise ValueError(f"raw_text exceeds the maximum size of {max_bytes} bytes")
        return value


class PostmortemBulkCreate(BaseModel):
    items: list[PostmortemCreate] = Field(min_length=1, max_length=MAX_BULK_POSTMORTEMS)


class PostmortemServiceLinkOut(BaseModel):
    service: ServiceOut
    role: ServiceLinkRole
    confidence: float | None


class PostmortemOut(BaseModel):
    id: uuid.UUID
    external_ref: str | None
    title: str
    occurred_at: datetime | None
    duration_minutes: int | None
    severity: Severity | None
    status: PostmortemStatus
    injection_flagged: bool
    failure_reason: str | None
    created_at: datetime
    # Defaulted, not required -- most call sites (search results, matched-postmortem
    # cards in a brief) validate this straight off the ORM row via from_attributes and
    # have no reason to resolve affected-service links; only Knowledge Base's own
    # list/detail views (postmortem_service.py) populate it with real data.
    affected_services: list[PostmortemServiceLinkOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PostmortemChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    section_label: str | None
    content: str
    char_start: int
    char_end: int

    model_config = {"from_attributes": True}


class PostmortemFactOut(BaseModel):
    fact_type: FactType
    statement: str
    confidence: float | None
    source_chunk_id: uuid.UUID
    char_start: int
    char_end: int


class PostmortemDetailOut(PostmortemOut):
    chunks: list[PostmortemChunkOut]
    redacted_text: str | None
    facts: list[PostmortemFactOut]


class PostmortemStatusOut(BaseModel):
    status: PostmortemStatus
    injection_flagged: bool
    failure_reason: str | None
