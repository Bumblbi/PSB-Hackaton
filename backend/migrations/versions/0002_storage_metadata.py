"""Normalize source metadata and preserve search attributes and evaluation results."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"

JSON_COLUMNS = (
    ("active_corpus", "payload"),
    ("document_versions", "payload"),
    ("messages", "answer_payload"),
    ("ingest_runs", "stats_json"),
)


def upgrade():
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.add_column(
        "document_versions",
        sa.Column("revision", sa.String(200), nullable=False, server_default=""),
    )
    op.add_column(
        "document_versions", sa.Column("source_name", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "document_versions",
        sa.Column("is_current_only", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("chunks", sa.Column("page", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("embedding", json_type, nullable=True))
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("test_id", sa.String(200), nullable=False),
        sa.Column("answer_status", sa.String(40), nullable=False),
        sa.Column("duration_ms", sa.Double(), nullable=False),
        sa.Column("checks_json", json_type, nullable=False),
    )
    op.create_index("ix_eval_runs_test_id", "eval_runs", ["test_id"])
    if op.get_bind().dialect.name == "postgresql":
        for table, column in JSON_COLUMNS:
            op.alter_column(
                table,
                column,
                type_=JSONB(),
                existing_type=sa.JSON(),
                postgresql_using=f"{column}::jsonb",
            )

    # The initial backend stored these values only inside the version snapshot.
    versions = sa.table(
        "document_versions",
        sa.column("id", sa.String()),
        sa.column("payload", json_type),
        sa.column("revision", sa.String()),
        sa.column("source_name", sa.Text()),
        sa.column("is_current_only", sa.Boolean()),
    )
    chunks = sa.table(
        "chunks",
        sa.column("id", sa.String()),
        sa.column("page", sa.Integer()),
        sa.column("embedding", json_type),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(versions.c.id, versions.c.payload)).mappings():
        payload = row["payload"]
        connection.execute(
            versions.update()
            .where(versions.c.id == row["id"])
            .values(
                revision=payload["revision"],
                source_name=payload["source_name"],
                is_current_only=payload.get("is_current_only", False),
            )
        )
        for chunk in payload["chunks"]:
            connection.execute(
                chunks.update()
                .where(chunks.c.id == str(chunk["chunk_id"]))
                .values(page=chunk.get("page"), embedding=chunk.get("embedding"))
            )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table, column in JSON_COLUMNS:
            op.alter_column(
                table,
                column,
                type_=sa.JSON(),
                existing_type=JSONB(),
                postgresql_using=f"{column}::json",
            )
    op.drop_table("eval_runs")
    op.drop_column("chunks", "embedding")
    op.drop_column("chunks", "page")
    op.drop_column("document_versions", "is_current_only")
    op.drop_column("document_versions", "source_name")
    op.drop_column("document_versions", "revision")
