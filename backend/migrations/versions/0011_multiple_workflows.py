"""Workflows reutilizaveis por categoria e por demanda."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_multiple_workflows"
down_revision: str | None = "0010_card_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "code", name="uq_workflow_org_code"),
        sa.UniqueConstraint("organization_id", "name", name="uq_workflow_org_name"),
        schema="app",
    )
    op.create_index("ix_workflows_organization_id", "workflows", ["organization_id"], schema="app")
    op.create_index("ix_workflows_one_default_per_org", "workflows", ["organization_id"], unique=True, schema="app", postgresql_where=sa.text("is_default AND active"))
    op.add_column("workflow_stages", sa.Column("workflow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.workflows.id", ondelete="CASCADE")), schema="app")
    op.add_column("demand_categories", sa.Column("default_workflow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.workflows.id", ondelete="RESTRICT")), schema="app")
    op.add_column("demands", sa.Column("workflow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.workflows.id", ondelete="RESTRICT")), schema="app")
    op.create_index("ix_workflow_stages_workflow_id", "workflow_stages", ["workflow_id"], schema="app")
    op.create_index("ix_demand_categories_default_workflow_id", "demand_categories", ["default_workflow_id"], schema="app")
    op.create_index("ix_demands_workflow_id", "demands", ["workflow_id"], schema="app")

    op.execute(
        "INSERT INTO app.workflows "
        "(id, organization_id, name, code, description, is_default, active, revision) "
        "SELECT gen_random_uuid(), id, 'Fluxo padrão', 'PADRAO', "
        "'Fluxo migrado da operação existente.', true, true, 1 "
        "FROM app.organizations"
    )
    op.execute(
        "UPDATE app.workflow_stages AS stage SET workflow_id = workflow.id "
        "FROM app.workflows AS workflow "
        "WHERE workflow.organization_id = stage.organization_id AND workflow.is_default"
    )
    op.execute(
        "UPDATE app.demand_categories AS category SET default_workflow_id = workflow.id "
        "FROM app.workflows AS workflow "
        "WHERE workflow.organization_id = category.organization_id AND workflow.is_default"
    )
    op.execute(
        "UPDATE app.demands AS demand SET workflow_id = workflow.id "
        "FROM app.workflows AS workflow "
        "WHERE workflow.organization_id = demand.organization_id AND workflow.is_default"
    )
    op.alter_column("workflow_stages", "workflow_id", nullable=False, schema="app")
    op.alter_column("demands", "workflow_id", nullable=False, schema="app")
    op.drop_constraint("uq_workflow_stage_org_code", "workflow_stages", schema="app", type_="unique")
    op.create_unique_constraint("uq_workflow_stage_workflow_code", "workflow_stages", ["workflow_id", "code"], schema="app")


def downgrade() -> None:
    op.drop_constraint("uq_workflow_stage_workflow_code", "workflow_stages", schema="app", type_="unique")
    op.create_unique_constraint("uq_workflow_stage_org_code", "workflow_stages", ["organization_id", "code"], schema="app")
    op.drop_index("ix_demands_workflow_id", table_name="demands", schema="app")
    op.drop_index("ix_demand_categories_default_workflow_id", table_name="demand_categories", schema="app")
    op.drop_index("ix_workflow_stages_workflow_id", table_name="workflow_stages", schema="app")
    op.drop_column("demands", "workflow_id", schema="app")
    op.drop_column("demand_categories", "default_workflow_id", schema="app")
    op.drop_column("workflow_stages", "workflow_id", schema="app")
    op.drop_index("ix_workflows_one_default_per_org", table_name="workflows", schema="app")
    op.drop_index("ix_workflows_organization_id", table_name="workflows", schema="app")
    op.drop_table("workflows", schema="app")
