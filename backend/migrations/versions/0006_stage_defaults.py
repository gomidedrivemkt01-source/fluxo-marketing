"""Responsavel padrao e previsao automatica por etapa."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_stage_defaults"
down_revision: str | None = "0005_briefings_checklists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_stages",
        sa.Column(
            "default_assignee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        schema="app",
    )
    op.add_column(
        "workflow_stages",
        sa.Column("expected_duration_hours", sa.Integer()),
        schema="app",
    )
    op.create_index(
        "ix_workflow_stages_default_assignee_id",
        "workflow_stages",
        ["default_assignee_id"],
        schema="app",
    )
    op.create_check_constraint(
        "ck_workflow_stage_expected_duration_positive",
        "workflow_stages",
        "expected_duration_hours IS NULL OR expected_duration_hours > 0",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_workflow_stage_expected_duration_positive",
        "workflow_stages",
        schema="app",
        type_="check",
    )
    op.drop_index(
        "ix_workflow_stages_default_assignee_id",
        table_name="workflow_stages",
        schema="app",
    )
    op.drop_column("workflow_stages", "expected_duration_hours", schema="app")
    op.drop_column("workflow_stages", "default_assignee_id", schema="app")
