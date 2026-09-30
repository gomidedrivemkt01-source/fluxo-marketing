"""Versoes imutaveis de workflow vinculadas as demandas."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_workflow_versions"
down_revision: str | None = "0011_multiple_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.workflows.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_version_number"),
        schema="app",
    )
    op.create_index(
        "ix_workflow_versions_organization_id",
        "workflow_versions",
        ["organization_id"],
        schema="app",
    )
    op.create_index(
        "ix_workflow_versions_workflow_id",
        "workflow_versions",
        ["workflow_id"],
        schema="app",
    )
    op.add_column(
        "demands",
        sa.Column(
            "workflow_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.workflow_versions.id", ondelete="RESTRICT"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_demands_workflow_version_id",
        "demands",
        ["workflow_version_id"],
        schema="app",
    )

    op.execute(
        """
        INSERT INTO app.workflow_versions
            (id, organization_id, workflow_id, version, definition)
        SELECT
            gen_random_uuid(),
            workflow.organization_id,
            workflow.id,
            1,
            jsonb_build_object(
                'stages',
                COALESCE(
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'id', stage.id::text,
                                'name', stage.name,
                                'code', stage.code,
                                'color', stage.color,
                                'position', stage.position,
                                'defaultAssigneeId', stage.default_assignee_id::text,
                                'expectedDurationHours', stage.expected_duration_hours
                            ) ORDER BY stage.position, stage.name
                        )
                        FROM app.workflow_stages AS stage
                        WHERE stage.workflow_id = workflow.id AND stage.active
                    ),
                    '[]'::jsonb
                )
            )
        FROM app.workflows AS workflow
        """
    )
    op.execute(
        """
        UPDATE app.demands AS demand
        SET workflow_version_id = version.id
        FROM app.workflow_versions AS version
        WHERE version.workflow_id = demand.workflow_id AND version.version = 1
        """
    )
    op.alter_column("demands", "workflow_version_id", nullable=False, schema="app")


def downgrade() -> None:
    op.drop_index("ix_demands_workflow_version_id", table_name="demands", schema="app")
    op.drop_column("demands", "workflow_version_id", schema="app")
    op.drop_index(
        "ix_workflow_versions_workflow_id",
        table_name="workflow_versions",
        schema="app",
    )
    op.drop_index(
        "ix_workflow_versions_organization_id",
        table_name="workflow_versions",
        schema="app",
    )
    op.drop_table("workflow_versions", schema="app")
