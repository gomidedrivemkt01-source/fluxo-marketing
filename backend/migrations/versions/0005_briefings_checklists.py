"""Briefings por categoria e checklists por etapa."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_briefings_checklists"
down_revision: str | None = "0004_shared_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "briefing_fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.demand_categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("help_text", sa.Text()),
        sa.Column("field_type", sa.String(30), server_default="text", nullable=False),
        sa.Column("options", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("category_id", "key", name="uq_briefing_field_category_key"),
        schema="app",
    )
    op.create_index("ix_briefing_fields_organization_id", "briefing_fields", ["organization_id"], schema="app")
    op.create_index("ix_briefing_fields_category_id", "briefing_fields", ["category_id"], schema="app")
    op.create_table(
        "checklist_template_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workflow_stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.workflow_stages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="app",
    )
    op.create_index("ix_checklist_template_items_organization_id", "checklist_template_items", ["organization_id"], schema="app")
    op.create_index("ix_checklist_template_items_workflow_stage_id", "checklist_template_items", ["workflow_stage_id"], schema="app")
    op.create_table(
        "demand_briefing_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.demands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.briefing_fields.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("value", postgresql.JSONB()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("demand_id", "field_id", name="uq_demand_briefing_answer"),
        schema="app",
    )
    op.create_index("ix_demand_briefing_answers_demand_id", "demand_briefing_answers", ["demand_id"], schema="app")
    op.create_index("ix_demand_briefing_answers_field_id", "demand_briefing_answers", ["field_id"], schema="app")
    op.create_table(
        "demand_checklist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.demands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.checklist_template_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("completed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("completed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("demand_id", "template_item_id", name="uq_demand_checklist_item"),
        schema="app",
    )
    op.create_index("ix_demand_checklist_items_demand_id", "demand_checklist_items", ["demand_id"], schema="app")
    op.create_index("ix_demand_checklist_items_template_item_id", "demand_checklist_items", ["template_item_id"], schema="app")


def downgrade() -> None:
    op.drop_table("demand_checklist_items", schema="app")
    op.drop_table("demand_briefing_answers", schema="app")
    op.drop_table("checklist_template_items", schema="app")
    op.drop_table("briefing_fields", schema="app")
