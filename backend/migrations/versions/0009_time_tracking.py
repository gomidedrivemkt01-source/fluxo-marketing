"""Apontamentos de tempo, timer e esforço previsto."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_time_tracking"
down_revision: str | None = "0008_private_demand_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "demands",
        sa.Column("expected_effort_minutes", sa.Integer()),
        schema="app",
    )
    op.create_check_constraint(
        "ck_demand_expected_effort_positive",
        "demands",
        "expected_effort_minutes IS NULL OR expected_effort_minutes > 0",
        schema="app",
    )

    op.create_table(
        "time_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "demand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("note", sa.Text()),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source IN ('MANUAL', 'TIMER')", name="ck_time_entry_source"),
        sa.CheckConstraint("state IN ('RUNNING', 'COMPLETED')", name="ck_time_entry_state"),
        sa.CheckConstraint(
            "(state = 'RUNNING' AND ended_at IS NULL AND duration_minutes IS NULL) OR "
            "(state = 'COMPLETED' AND ended_at IS NOT NULL AND duration_minutes > 0)",
            name="ck_time_entry_state_values",
        ),
        schema="app",
    )
    op.create_index(
        "ix_time_entries_organization_id",
        "time_entries",
        ["organization_id"],
        schema="app",
    )
    op.create_index("ix_time_entries_demand_id", "time_entries", ["demand_id"], schema="app")
    op.create_index(
        "ix_time_entries_user_profile_id",
        "time_entries",
        ["user_profile_id"],
        schema="app",
    )
    op.create_index(
        "ix_time_entries_demand_started",
        "time_entries",
        ["demand_id", "started_at"],
        schema="app",
    )
    op.create_index(
        "ix_time_entries_one_running_per_user",
        "time_entries",
        ["user_profile_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("state = 'RUNNING' AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_time_entries_one_running_per_user", table_name="time_entries", schema="app")
    op.drop_index("ix_time_entries_demand_started", table_name="time_entries", schema="app")
    op.drop_index("ix_time_entries_user_profile_id", table_name="time_entries", schema="app")
    op.drop_index("ix_time_entries_demand_id", table_name="time_entries", schema="app")
    op.drop_index("ix_time_entries_organization_id", table_name="time_entries", schema="app")
    op.drop_table("time_entries", schema="app")
    op.drop_constraint("ck_demand_expected_effort_positive", "demands", schema="app", type_="check")
    op.drop_column("demands", "expected_effort_minutes", schema="app")
