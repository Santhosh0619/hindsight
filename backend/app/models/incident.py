import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_values


class IncidentStatus(enum.StrEnum):
    OPEN = "open"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class BriefStatus(enum.StrEnum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class FeedbackVerdict(enum.StrEnum):
    HELPFUL = "helpful"
    PARTIALLY = "partially"
    UNHELPFUL = "unhelpful"


class Incident(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_workspace_status", "workspace_id", "status"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_alert_text: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", values_callable=enum_values),
        nullable=False,
        default=IncidentStatus.OPEN,
    )
    opened_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentSignal(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "incident_signals"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symptoms: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    error_strings: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    affected_service_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    time_window: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    extracted_by_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class Brief(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "briefs"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[BriefStatus] = mapped_column(
        Enum(BriefStatus, name="brief_status", values_callable=enum_values),
        nullable=False,
        default=BriefStatus.GENERATING,
    )
    hypotheses: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    matched_postmortems: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    blast_radius: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    runbook_steps: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    page_list: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    citations: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    correction_passes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    from_cache: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BriefFeedback(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "brief_feedback"

    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[FeedbackVerdict] = mapped_column(
        Enum(FeedbackVerdict, name="feedback_verdict", values_callable=enum_values), nullable=False
    )
    correct_postmortem_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postmortems.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
