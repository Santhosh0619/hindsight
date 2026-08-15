import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class EvalCase(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "eval_cases"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    incident_text: Mapped[str] = mapped_column(String, nullable=False)
    expected_postmortem_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    expected_service_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    notes: Mapped[str | None] = mapped_column(String, nullable=True)


class EvalRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "eval_runs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recall_at_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall_at_5: Mapped[float | None] = mapped_column(Float, nullable=True)
    mrr: Mapped[float | None] = mapped_column(Float, nullable=True)
    groundedness: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_validity: Mapped[float | None] = mapped_column(Float, nullable=True)
    cases_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)


class EvalCaseResult(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "eval_case_results"

    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    eval_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    retrieved_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    rank_of_first_hit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    groundedness: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
