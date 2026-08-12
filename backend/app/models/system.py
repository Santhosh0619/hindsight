import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import EmbeddingVector


class SemanticCache(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "semantic_cache"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector, nullable=True)
    response: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
