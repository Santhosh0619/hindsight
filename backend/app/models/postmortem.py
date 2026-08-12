import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import EmbeddingVector, enum_values


class Severity(enum.StrEnum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"


class PostmortemStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class FactType(enum.StrEnum):
    TRIGGER = "trigger"
    ROOT_CAUSE = "root_cause"
    REMEDIATION = "remediation"
    DETECTION_GAP = "detection_gap"
    CONTRIBUTING_FACTOR = "contributing_factor"


class ServiceLinkRole(enum.StrEnum):
    ROOT_CAUSE = "root_cause"
    AFFECTED = "affected"
    DOWNSTREAM = "downstream"


class Postmortem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "postmortems"
    __table_args__ = (Index("ix_postmortems_workspace_status", "workspace_id", "status"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[Severity | None] = mapped_column(
        Enum(Severity, name="severity", values_callable=enum_values), nullable=True
    )
    raw_text: Mapped[str] = mapped_column(String, nullable=False)
    redacted_text: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[PostmortemStatus] = mapped_column(
        Enum(PostmortemStatus, name="postmortem_status", values_callable=enum_values),
        nullable=False,
        default=PostmortemStatus.PENDING,
    )
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    injection_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PostmortemChunk(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "postmortem_chunks"
    __table_args__ = (
        Index(
            "ix_postmortem_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_postmortem_chunks_tsv_gin", "tsv", postgresql_using="gin"),
    )

    postmortem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("postmortems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector, nullable=True)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)


class FailureMode(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "failure_modes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "label", name="uq_failure_modes_workspace_label"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_description: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)


class PostmortemFact(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "postmortem_facts"

    postmortem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("postmortems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fact_type: Mapped[FactType] = mapped_column(
        Enum(FactType, name="fact_type", values_callable=enum_values), nullable=False
    )
    statement: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postmortem_chunks.id", ondelete="CASCADE"), nullable=False
    )
    extracted_by_model: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PostmortemService(Base):
    __tablename__ = "postmortem_services"

    postmortem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postmortems.id", ondelete="CASCADE"), primary_key=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ServiceLinkRole] = mapped_column(
        Enum(ServiceLinkRole, name="service_link_role", values_callable=enum_values),
        primary_key=True,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class PostmortemFailureMode(Base):
    __tablename__ = "postmortem_failure_modes"

    postmortem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postmortems.id", ondelete="CASCADE"), primary_key=True
    )
    failure_mode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("failure_modes.id", ondelete="CASCADE"), primary_key=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
