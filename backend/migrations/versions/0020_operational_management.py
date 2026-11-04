"""Retirada operacional preserva os registros usados pelo historico."""

import sqlalchemy as sa
from alembic import op

revision = "0020_operational_management"
down_revision = "0019_local_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("memberships", "workflows", "workflow_stages"):
        op.add_column(table, sa.Column("removed_at", sa.DateTime(timezone=True)), schema="app")


def downgrade() -> None:
    for table in ("workflow_stages", "workflows", "memberships"):
        op.drop_column(table, "removed_at", schema="app")
