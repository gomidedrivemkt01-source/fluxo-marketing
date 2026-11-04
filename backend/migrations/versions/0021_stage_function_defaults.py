"""Padrões operacionais por etapa preservam as versões históricas do workflow."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_stage_function_defaults"
down_revision: str | None = "0020_operational_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "demand_stage_instances",
        sa.Column("assignment_defaults", postgresql.JSONB(), nullable=True),
        schema="app",
    )


def downgrade() -> None:
    op.drop_column("demand_stage_instances", "assignment_defaults", schema="app")
