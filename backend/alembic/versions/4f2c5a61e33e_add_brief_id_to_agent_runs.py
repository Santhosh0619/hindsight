"""add brief_id to agent_runs

Revision ID: 4f2c5a61e33e
Revises: 6e621b073457
Create Date: 2026-08-15 16:29:36.461349

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "4f2c5a61e33e"
down_revision: str | None = "6e621b073457"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("brief_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_agent_runs_brief_id_briefs",
        "agent_runs",
        "briefs",
        ["brief_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_runs_brief_id_briefs", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "brief_id")
