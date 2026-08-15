"""add mode to eval_runs

Revision ID: 6e621b073457
Revises: 26904cf682b7
Create Date: 2026-08-15 11:50:20.759327

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6e621b073457"
down_revision: str | None = "26904cf682b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("eval_runs", sa.Column("mode", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("eval_runs", "mode")
