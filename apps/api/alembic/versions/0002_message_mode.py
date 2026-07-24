"""Add the per-question mode marker to messages.

Compare-mode questions and answers are ordinary messages; the nullable mode
column only records how they were produced so the client can render
per-document sections. Existing rows stay NULL (the default answer mode).

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("mode", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "mode")
