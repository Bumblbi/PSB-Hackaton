"""Initial backend schema (frozen table definitions for repeatable upgrades)."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
    )
    op.create_table(
        "active_corpus",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index("ix_document_versions_source_hash", "document_versions", ["source_hash"])
    op.create_index("ix_versions_validity", "document_versions", ["document_id", "valid_from"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "version_id", sa.String(36), sa.ForeignKey("document_versions.id"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_index("ix_chunks_version_id", "chunks", ["version_id"])
    op.create_table(
        "document_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "parent_document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False
        ),
        sa.Column(
            "related_document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False
        ),
        sa.Column("relation_type", sa.String(30), nullable=False),
    )
    op.create_table(
        "chats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("answer_payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("chat_id", "ordinal", name="uq_messages_chat_ordinal"),
    )
    op.create_index("ix_messages_chat_id", "messages", ["chat_id"])
    op.create_table(
        "answer_citations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("chunk_id", sa.String(36), sa.ForeignKey("chunks.id"), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
    )
    op.create_index("ix_answer_citations_message_id", "answer_citations", ["message_id"])
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("corpus_hash", sa.String(64)),
        sa.Column("stats_json", sa.JSON(), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE INDEX ix_chunks_fts ON chunks USING gin (to_tsvector('russian', text))")


def downgrade():
    for table in (
        "ingest_runs",
        "answer_citations",
        "messages",
        "chats",
        "document_links",
        "chunks",
        "document_versions",
        "active_corpus",
        "documents",
    ):
        op.drop_table(table)
