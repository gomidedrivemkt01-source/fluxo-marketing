"""Demandas e associação manual de importações de Daily."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_demands_daily_imports"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demand_counters",
        sa.Column("year", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("last_value", sa.Integer(), server_default="0", nullable=False),
        schema="app",
    )
    op.create_table(
        "demands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("public_id", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "primary_company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.companies.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demand_categories.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "current_assignee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column("status", sa.String(40), server_default="WAITING_EXECUTION", nullable=False),
        sa.Column("priority", sa.String(20), server_default="NORMAL", nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("forecast_at", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(30), server_default="interface", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("organization_id", "public_id", name="uq_demand_org_public_id"),
        schema="app",
    )
    op.create_index("ix_demands_organization_id", "demands", ["organization_id"], schema="app")
    op.create_index("ix_demands_public_id", "demands", ["public_id"], schema="app")
    op.create_index(
        "ix_demands_primary_company_id", "demands", ["primary_company_id"], schema="app"
    )
    op.create_index("ix_demands_category_id", "demands", ["category_id"], schema="app")
    op.create_index(
        "ix_demands_current_assignee_id", "demands", ["current_assignee_id"], schema="app"
    )

    op.create_table(
        "daily_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("batch_id", sa.String(100), nullable=False),
        sa.Column("source_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_label", sa.String(200), nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("document_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(30), server_default="reviewing", nullable=False),
        sa.Column("raw_document", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "document_hash", name="uq_daily_import_org_hash"),
        schema="app",
    )
    op.create_index(
        "ix_daily_imports_organization_id", "daily_imports", ["organization_id"], schema="app"
    )

    op.create_table(
        "daily_import_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "daily_import_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.daily_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_item_id", sa.String(100), nullable=False),
        sa.Column("title_hint", sa.String(300), nullable=False),
        sa.Column("company_hint", sa.String(200)),
        sa.Column("card_id_hint", sa.String(32)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=False),
        sa.Column("proposals", postgresql.JSONB(), nullable=False),
        sa.Column("mapping_action", sa.String(20), server_default="pending", nullable=False),
        sa.Column(
            "target_demand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demands.id", ondelete="RESTRICT"),
        ),
        sa.Column("new_demand_title", sa.String(300)),
        sa.Column("mapping_note", sa.Text()),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("daily_import_id", "source_item_id", name="uq_daily_item_source"),
        sa.UniqueConstraint("daily_import_id", "ordinal", name="uq_daily_item_ordinal"),
        schema="app",
    )
    op.create_index(
        "ix_daily_import_items_import", "daily_import_items", ["daily_import_id"], schema="app"
    )
    op.create_index(
        "ix_daily_import_items_demand", "daily_import_items", ["target_demand_id"], schema="app"
    )

    op.create_table(
        "demand_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "demand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "daily_import_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.daily_import_items.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="app",
    )
    op.create_index("ix_demand_updates_demand", "demand_updates", ["demand_id"], schema="app")
    op.create_index(
        "ix_demand_updates_import_item", "demand_updates", ["daily_import_item_id"], schema="app"
    )


def downgrade() -> None:
    for table in [
        "demand_updates",
        "daily_import_items",
        "daily_imports",
        "demands",
        "demand_counters",
    ]:
        op.drop_table(table, schema="app")
