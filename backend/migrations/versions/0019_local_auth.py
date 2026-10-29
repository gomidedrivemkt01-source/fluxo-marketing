"""Credenciais locais substituem o Supabase Auth."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_local_auth"
down_revision: str | None = "0018_trello_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "user_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("password_changed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="app",
    )
    op.create_index(
        "ix_auth_users_email_lower",
        "auth_users",
        [sa.text("lower(email)")],
        unique=True,
        schema="app",
    )
    # Os tokens do Supabase deixam de existir; a sessão do app passa a ser a única credencial.
    op.alter_column("app_sessions", "access_token_ciphertext", nullable=True, schema="app")
    op.alter_column("app_sessions", "refresh_token_ciphertext", nullable=True, schema="app")


def downgrade() -> None:
    op.execute(
        "UPDATE app.app_sessions SET access_token_ciphertext = '', refresh_token_ciphertext = '' "
        "WHERE access_token_ciphertext IS NULL OR refresh_token_ciphertext IS NULL"
    )
    op.alter_column("app_sessions", "refresh_token_ciphertext", nullable=False, schema="app")
    op.alter_column("app_sessions", "access_token_ciphertext", nullable=False, schema="app")
    op.drop_index("ix_auth_users_email_lower", table_name="auth_users", schema="app")
    op.drop_table("auth_users", schema="app")
