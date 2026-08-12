import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_values


class ServiceTier(int, enum.Enum):
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


class EdgeKind(enum.StrEnum):
    CALLS = "calls"
    READS_FROM = "reads_from"
    PUBLISHES_TO = "publishes_to"
    DEPENDS_ON = "depends_on"


class EdgeCriticality(enum.StrEnum):
    HARD = "hard"
    SOFT = "soft"


class Team(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "teams"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slack_handle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    escalation_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Service(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_services_workspace_name"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tier: Mapped[ServiceTier] = mapped_column(
        Enum(ServiceTier, name="service_tier"), nullable=False
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    repo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    runbook_url: Mapped[str | None] = mapped_column(String, nullable=True)


class ServiceEdge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "service_edges"
    __table_args__ = (
        UniqueConstraint(
            "from_service_id", "to_service_id", "kind", name="uq_service_edges_from_to_kind"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[EdgeKind] = mapped_column(
        Enum(EdgeKind, name="edge_kind", values_callable=enum_values), nullable=False
    )
    criticality: Mapped[EdgeCriticality] = mapped_column(
        Enum(EdgeCriticality, name="edge_criticality", values_callable=enum_values), nullable=False
    )
