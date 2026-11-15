"""Local accounts, revocable sessions and private chat ownership."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "auth_throttle",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    # SQLite supports an inline nullable FK without rebuilding a referenced chats table.
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE chats ADD COLUMN owner_id VARCHAR(36) REFERENCES users(id)")
    else:
        op.add_column("chats", sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id")))
    op.create_index("ix_chats_owner_id", "chats", ["owner_id"])


def downgrade():
    op.drop_index("ix_chats_owner_id", table_name="chats")
    op.drop_column("chats", "owner_id")
    op.drop_table("auth_throttle")
    op.drop_table("auth_sessions")
    op.drop_table("users")
