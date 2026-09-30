"""Checklist livre por card e pausa do timer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_card_workspace"
down_revision: str | None = "0009_time_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demand_todo_items",
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
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "completed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("position > 0", name="ck_demand_todo_position_positive"),
        schema="app",
    )
    op.create_index("ix_demand_todo_items_organization_id", "demand_todo_items", ["organization_id"], schema="app")
    op.create_index("ix_demand_todo_items_demand_id", "demand_todo_items", ["demand_id"], schema="app")
    op.create_index("ix_demand_todo_items_demand_position", "demand_todo_items", ["demand_id", "position"], schema="app")

    op.drop_index("ix_time_entries_one_running_per_user", table_name="time_entries", schema="app")
    op.drop_constraint("ck_time_entry_state_values", "time_entries", schema="app", type_="check")
    op.drop_constraint("ck_time_entry_state", "time_entries", schema="app", type_="check")
    op.create_check_constraint(
        "ck_time_entry_state",
        "time_entries",
        "state IN ('RUNNING', 'PAUSED', 'COMPLETED')",
        schema="app",
    )
    op.create_check_constraint(
        "ck_time_entry_state_values",
        "time_entries",
        "(state = 'RUNNING' AND ended_at IS NULL) OR "
        "(state IN ('PAUSED', 'COMPLETED') AND ended_at IS NOT NULL AND duration_minutes > 0)",
        schema="app",
    )
    op.create_index(
        "ix_time_entries_one_active_per_user",
        "time_entries",
        ["user_profile_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("state IN ('RUNNING', 'PAUSED') AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.execute("UPDATE app.time_entries SET state = 'COMPLETED' WHERE state = 'PAUSED'")
    op.drop_index("ix_time_entries_one_active_per_user", table_name="time_entries", schema="app")
    op.drop_constraint("ck_time_entry_state_values", "time_entries", schema="app", type_="check")
    op.drop_constraint("ck_time_entry_state", "time_entries", schema="app", type_="check")
    op.create_check_constraint("ck_time_entry_state", "time_entries", "state IN ('RUNNING', 'COMPLETED')", schema="app")
    op.create_check_constraint(
        "ck_time_entry_state_values",
        "time_entries",
        "(state = 'RUNNING' AND ended_at IS NULL AND duration_minutes IS NULL) OR "
        "(state = 'COMPLETED' AND ended_at IS NOT NULL AND duration_minutes > 0)",
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
    op.drop_index("ix_demand_todo_items_demand_position", table_name="demand_todo_items", schema="app")
    op.drop_index("ix_demand_todo_items_demand_id", table_name="demand_todo_items", schema="app")
    op.drop_index("ix_demand_todo_items_organization_id", table_name="demand_todo_items", schema="app")
    op.drop_table("demand_todo_items", schema="app")
