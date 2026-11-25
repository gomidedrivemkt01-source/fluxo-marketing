"""Add configurable operational alerts and indexes for contribution analytics."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_analytics_alerts"
down_revision = "0022_parallel_timers_bulk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_policies",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("warning_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("due_soon", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("overdue", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("approvals", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("include_participating", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("warning_days BETWEEN 1 AND 90", name="ck_notification_warning_days"),
        schema="app",
    )
    op.create_index(
        "ix_stage_visits_contribution",
        "demand_stage_visits",
        ["organization_id", "assignee_id", "demand_id"],
        schema="app",
    )
    op.create_index(
        "ix_demand_updates_completion",
        "demand_updates",
        ["demand_id", "kind", "created_at"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index("ix_demand_updates_completion", table_name="demand_updates", schema="app")
    op.drop_index("ix_stage_visits_contribution", table_name="demand_stage_visits", schema="app")
    op.drop_table("notification_policies", schema="app")
