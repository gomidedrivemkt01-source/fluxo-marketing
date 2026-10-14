"""Importacao Trello, revisoes e retencao segura de dados."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_data_governance"
down_revision: str | None = "0014_clear_unknown_forecasts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trello_import_batches",
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
        sa.Column("board_id", sa.String(100), nullable=False),
        sa.Column("board_name", sa.String(200), nullable=False),
        sa.Column("document_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="applied"),
        sa.Column("total_cards", sa.Integer(), nullable=False),
        sa.Column("created_cards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_cards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_cards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_cards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "summary_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "changes_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("reverted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "document_hash", name="uq_trello_import_org_hash"),
        schema="app",
    )
    op.create_index(
        "ix_trello_import_batches_organization_id",
        "trello_import_batches",
        ["organization_id"],
        schema="app",
    )
    op.create_index(
        "ix_trello_import_org_created",
        "trello_import_batches",
        ["organization_id", "created_at"],
        schema="app",
    )

    op.create_table(
        "trello_card_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("board_id", sa.String(100), nullable=False),
        sa.Column("card_id", sa.String(100), nullable=False),
        sa.Column(
            "demand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "last_import_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.trello_import_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "organization_id", "board_id", "card_id", name="uq_trello_card_org_board_card"
        ),
        schema="app",
    )
    for column in ("organization_id", "demand_id"):
        op.create_index(
            f"ix_trello_card_links_{column}", "trello_card_links", [column], schema="app"
        )
    op.create_index("ix_trello_card_link_demand", "trello_card_links", ["demand_id"], schema="app")

    op.create_table(
        "demand_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="app",
    )
    op.create_index(
        "ix_demand_revisions_organization_id", "demand_revisions", ["organization_id"], schema="app"
    )
    op.create_index(
        "ix_demand_revisions_demand_id", "demand_revisions", ["demand_id"], schema="app"
    )
    op.create_index(
        "ix_demand_revision_org_created",
        "demand_revisions",
        ["organization_id", "created_at"],
        schema="app",
    )
    op.create_index(
        "ix_demand_revision_demand_created",
        "demand_revisions",
        ["demand_id", "created_at"],
        schema="app",
    )

    op.create_table(
        "data_retention_policies",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("automatic_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("completed_after_days", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("interval_days BETWEEN 30 AND 365", name="ck_retention_interval_days"),
        sa.CheckConstraint(
            "completed_after_days BETWEEN 30 AND 3650", name="ck_retention_completed_days"
        ),
        schema="app",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.capture_demand_revision()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        BEGIN
            IF TG_OP = 'UPDATE' AND OLD IS DISTINCT FROM NEW THEN
                INSERT INTO app.demand_revisions
                    (id, organization_id, demand_id, revision, operation, snapshot, created_at)
                VALUES
                    (gen_random_uuid(), OLD.organization_id, OLD.id, OLD.revision,
                     'UPDATE', to_jsonb(OLD), now());
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                INSERT INTO app.demand_revisions
                    (id, organization_id, demand_id, revision, operation, snapshot, created_at)
                VALUES
                    (gen_random_uuid(), OLD.organization_id, OLD.id, OLD.revision,
                     'DELETE', to_jsonb(OLD), now());
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_capture_demand_revision
        BEFORE UPDATE OR DELETE ON app.demands
        FOR EACH ROW EXECUTE FUNCTION app.capture_demand_revision();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_capture_demand_revision ON app.demands")
    op.execute("DROP FUNCTION IF EXISTS app.capture_demand_revision()")
    op.drop_table("data_retention_policies", schema="app")
    op.drop_table("demand_revisions", schema="app")
    op.drop_table("trello_card_links", schema="app")
    op.drop_table("trello_import_batches", schema="app")
