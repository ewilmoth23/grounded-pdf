"""Initial GroundedPDF schema.

Revision ID: 0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


status_enum = sa.Enum(
    "QUEUED",
    "PROCESSING",
    "READY",
    "FAILED",
    "DELETED",
    name="processingstatus",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "application_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False, unique=True),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("searchable_page_count", sa.Integer(), nullable=False),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_table(
        "conversation_documents",
        sa.Column(
            "conversation_id",
            sa.String(length=36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_conversation_documents_document_id", "conversation_documents", ["document_id"]
    )
    op.create_table(
        "document_pages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.String(length=30), nullable=False),
        sa.Column("is_searchable", sa.Boolean(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("document_id", "page_number"),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "page_id",
            sa.String(length=36),
            sa.ForeignKey("document_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("embedding_id", sa.String(length=100), nullable=False, unique=True),
        sa.Column("extraction_method", sa.String(length=30), nullable=False),
        sa.UniqueConstraint("document_id", "page_number", "chunk_index"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_page_id", "document_chunks", ["page_id"])
    op.create_index("ix_chunks_document_page", "document_chunks", ["document_id", "page_number"])
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(length=36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("USER", "ASSISTANT", name="messagerole", native_enum=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_processing_jobs_document_id", "processing_jobs", ["document_id"])
    op.create_table(
        "citations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "message_id",
            sa.String(length=36),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("retrieval_score", sa.Float(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.UniqueConstraint("message_id", "ordinal"),
    )
    op.create_index("ix_citations_message_id", "citations", ["message_id"])
    op.create_index("ix_citations_document_id", "citations", ["document_id"])


def downgrade() -> None:
    for table in (
        "citations",
        "processing_jobs",
        "messages",
        "document_chunks",
        "document_pages",
        "conversation_documents",
        "documents",
        "conversations",
        "application_settings",
    ):
        op.drop_table(table)
    sa.Enum(name="messagerole", native_enum=False).drop(op.get_bind(), checkfirst=True)
    status_enum.drop(op.get_bind(), checkfirst=True)
