"""Dois timers por pessoa e identificação idempotente dos lotes de demandas."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_parallel_timers_bulk"
down_revision = "0021_stage_function_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "time_entries",
        sa.Column("timer_slot", sa.Integer(), nullable=False, server_default="1"),
        schema="app",
    )
    op.create_check_constraint(
        "ck_timer_slot", "time_entries", "timer_slot IN (1, 2)", schema="app"
    )
    op.drop_index("ix_time_entries_one_active_per_user", table_name="time_entries", schema="app")
    for name, columns in (
        ("uq_active_timer_slot", ["organization_id", "user_profile_id", "timer_slot"]),
        ("uq_active_timer_demand", ["organization_id", "user_profile_id", "demand_id"]),
    ):
        op.create_index(
            name,
            "time_entries",
            columns,
            unique=True,
            schema="app",
            postgresql_where=sa.text("state IN ('RUNNING', 'PAUSED') AND deleted_at IS NULL"),
        )
    op.create_table(
        "bulk_demand_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("batch_key", sa.String(160), nullable=False),
        sa.Column("document_hash", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("organization_id", "batch_key", name="uq_bulk_batch_key"),
        schema="app",
    )
    op.create_table(
        "bulk_demand_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.bulk_demand_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_key", sa.String(160), nullable=False),
        sa.Column(
            "demand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("organization_id", "external_key", name="uq_bulk_demand_external_key"),
        schema="app",
    )


def downgrade() -> None:
    # A volta não pode apagar a rastreabilidade de lotes nem descartar um timer aberto.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM app.bulk_demand_batches)")):
        raise RuntimeError(
            "Existem lotes registrados. Preserve seus vínculos antes de reverter a estrutura."
        )
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM app.time_entries WHERE state IN ('RUNNING','PAUSED') AND deleted_at IS NULL GROUP BY user_profile_id HAVING count(*) > 1)"
        )
    ):
        raise RuntimeError("Finalize o segundo timer antes de reverter esta migration.")
    op.drop_table("bulk_demand_items", schema="app")
    op.drop_table("bulk_demand_batches", schema="app")
    for name in ("uq_active_timer_slot", "uq_active_timer_demand"):
        op.drop_index(name, table_name="time_entries", schema="app")
    op.create_index(
        "ix_time_entries_one_active_per_user",
        "time_entries",
        ["user_profile_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("state IN ('RUNNING','PAUSED') AND deleted_at IS NULL"),
    )
    op.drop_constraint("ck_timer_slot", "time_entries", schema="app", type_="check")
    op.drop_column("time_entries", "timer_slot", schema="app")
