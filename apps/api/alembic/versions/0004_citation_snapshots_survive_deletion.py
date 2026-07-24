"""Let citation snapshots survive document deletion.

``citations.document_id`` becomes nullable with ``ON DELETE SET NULL`` so that
deleting a document no longer erases the evidence trail of historical answers.
The snapshot columns (``document_name``, ``page_number``, ``excerpt``) stay NOT
NULL, keeping old citations renderable after their source document is gone.

SQLite cannot alter foreign keys in place, so the table is recreated through
Alembic batch mode. A naming convention gives the reflected unnamed foreign key
a deterministic name purely so it can be dropped and recreated; constraint
comparison in the migration test matches on columns, not names.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMING_CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
DOCUMENT_FK = "fk_citations_document_id_documents"


def upgrade() -> None:
    with op.batch_alter_table(
        "citations", recreate="always", naming_convention=NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint(DOCUMENT_FK, type_="foreignkey")
        batch_op.alter_column("document_id", existing_type=sa.String(length=36), nullable=True)
        batch_op.create_foreign_key(
            DOCUMENT_FK, "documents", ["document_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    # Rows whose document was deleted cannot satisfy a NOT NULL cascade FK.
    op.execute(sa.text("DELETE FROM citations WHERE document_id IS NULL"))
    with op.batch_alter_table(
        "citations", recreate="always", naming_convention=NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint(DOCUMENT_FK, type_="foreignkey")
        batch_op.alter_column("document_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_foreign_key(
            DOCUMENT_FK, "documents", ["document_id"], ["id"], ondelete="CASCADE"
        )
