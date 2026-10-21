"""Permite escolher uma imagem de capa por demanda."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_demand_file_cover"
down_revision: str | None = "0016_workflow_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "demand_files",
        sa.Column("is_cover", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="app",
    )
    op.create_index(
        "uq_demand_file_active_cover",
        "demand_files",
        ["demand_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("is_cover AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_demand_file_active_cover", table_name="demand_files", schema="app")
    op.drop_column("demand_files", "is_cover", schema="app")
