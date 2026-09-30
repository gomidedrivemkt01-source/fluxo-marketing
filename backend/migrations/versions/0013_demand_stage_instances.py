"""Plano operacional e agenda por etapa da demanda."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_demand_stage_instances"
down_revision: str | None = "0012_workflow_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demand_stage_instances",
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
            "workflow_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.workflow_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workflow_stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.workflow_stages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="upcoming"),
        sa.Column(
            "assignee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("forecast_at", sa.DateTime(timezone=True)),
        sa.Column("entered_at", sa.DateTime(timezone=True)),
        sa.Column("left_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "state IN ('completed', 'current', 'upcoming', 'skipped')",
            name="ck_demand_stage_instance_state",
        ),
        sa.UniqueConstraint(
            "demand_id",
            "workflow_version_id",
            "workflow_stage_id",
            name="uq_demand_stage_instance",
        ),
        schema="app",
    )
    for column in ("organization_id", "demand_id", "workflow_version_id", "workflow_stage_id", "assignee_id"):
        op.create_index(
            f"ix_demand_stage_instances_{column}",
            "demand_stage_instances",
            [column],
            schema="app",
        )
    op.create_index(
        "ix_demand_stage_instances_demand_position",
        "demand_stage_instances",
        ["demand_id", "position"],
        schema="app",
    )
    op.execute(
        """
        INSERT INTO app.demand_stage_instances (
            id, organization_id, demand_id, workflow_version_id, workflow_stage_id,
            position, state, assignee_id, deadline_at, forecast_at, entered_at
        )
        SELECT
            gen_random_uuid(), demand.organization_id, demand.id, version.id,
            (stage.item->>'id')::uuid, (stage.item->>'position')::integer,
            CASE
                WHEN (stage.item->>'id')::uuid = demand.current_stage_id THEN 'current'
                WHEN (stage.item->>'position')::integer < current_stage.position THEN 'completed'
                ELSE 'upcoming'
            END,
            CASE
                WHEN (stage.item->>'id')::uuid = demand.current_stage_id
                    THEN demand.current_assignee_id
                ELSE NULLIF(stage.item->>'defaultAssigneeId', '')::uuid
            END,
            CASE WHEN (stage.item->>'id')::uuid = demand.current_stage_id THEN demand.deadline_at END,
            CASE WHEN (stage.item->>'id')::uuid = demand.current_stage_id THEN demand.forecast_at END,
            CASE WHEN (stage.item->>'id')::uuid = demand.current_stage_id THEN demand.created_at END
        FROM app.demands AS demand
        JOIN app.workflow_versions AS version ON version.id = demand.workflow_version_id
        CROSS JOIN LATERAL jsonb_array_elements(version.definition->'stages') AS stage(item)
        LEFT JOIN LATERAL (
            SELECT (current_item->>'position')::integer AS position
            FROM jsonb_array_elements(version.definition->'stages') AS current_item
            WHERE (current_item->>'id')::uuid = demand.current_stage_id
            LIMIT 1
        ) AS current_stage ON TRUE
        """
    )
    op.execute(
        """
        WITH stage_forecasts AS (
            SELECT
                demand.id AS demand_id,
                (target.item->>'id')::uuid AS workflow_stage_id,
                COALESCE(demand.forecast_at, demand.created_at)
                    + make_interval(
                        hours => COALESCE(
                            (
                                SELECT SUM(COALESCE((future.item->>'expectedDurationHours')::integer, 0))::integer
                                FROM jsonb_array_elements(version.definition->'stages') AS future(item)
                                WHERE (future.item->>'position')::integer > current_stage.position
                                  AND (future.item->>'position')::integer <= (target.item->>'position')::integer
                            ),
                            0
                        )
                    ) AS forecast_at
            FROM app.demands AS demand
            JOIN app.workflow_versions AS version ON version.id = demand.workflow_version_id
            CROSS JOIN LATERAL jsonb_array_elements(version.definition->'stages') AS target(item)
            JOIN LATERAL (
                SELECT (current_item->>'position')::integer AS position
                FROM jsonb_array_elements(version.definition->'stages') AS current_item
                WHERE (current_item->>'id')::uuid = demand.current_stage_id
                LIMIT 1
            ) AS current_stage ON TRUE
            WHERE (target.item->>'position')::integer > current_stage.position
              AND target.item->>'expectedDurationHours' IS NOT NULL
        )
        UPDATE app.demand_stage_instances AS instance
        SET forecast_at = stage_forecasts.forecast_at
        FROM stage_forecasts
        WHERE instance.demand_id = stage_forecasts.demand_id
          AND instance.workflow_stage_id = stage_forecasts.workflow_stage_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_demand_stage_instances_demand_position", table_name="demand_stage_instances", schema="app")
    for column in ("assignee_id", "workflow_stage_id", "workflow_version_id", "demand_id", "organization_id"):
        op.drop_index(
            f"ix_demand_stage_instances_{column}",
            table_name="demand_stage_instances",
            schema="app",
        )
    op.drop_table("demand_stage_instances", schema="app")
