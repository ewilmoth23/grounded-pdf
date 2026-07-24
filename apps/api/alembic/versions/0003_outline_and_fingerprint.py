"""Add the document outline and index fingerprint columns.

The outline is presentation metadata: PDF bookmarks captured at ingestion so
the viewer can offer section navigation. The index fingerprint records the
embedding model and chunk geometry the current vectors were built with, so the
application can flag documents whose index no longer matches the runtime
settings. Existing rows stay NULL (no outline; legacy index of unknown
provenance, treated as stale).

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("outline_json", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("index_fingerprint", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "index_fingerprint")
    op.drop_column("documents", "outline_json")
