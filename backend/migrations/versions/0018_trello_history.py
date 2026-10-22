"""Preserva comentários, eventos, checklists e anexos externos do Trello."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_trello_history"
down_revision: str | None = "0017_demand_file_cover"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_source_columns(table: str) -> None:
    op.add_column(table, sa.Column("source_system", sa.String(30)), schema="app")
    op.add_column(table, sa.Column("external_id", sa.String(100)), schema="app")
    op.add_column(
        table,
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "app.trello_import_batches.id",
                name=f"fk_{table}_import_batch",
                ondelete="SET NULL",
            ),
        ),
        schema="app",
    )
    op.create_index(f"ix_{table}_import_batch_id", table, ["import_batch_id"], schema="app")


def upgrade() -> None:
    _add_source_columns("comments")
    op.create_unique_constraint(
        "uq_comment_external", "comments", ["source_system", "external_id"], schema="app"
    )

    _add_source_columns("demand_updates")
    op.create_unique_constraint(
        "uq_demand_update_external",
        "demand_updates",
        ["source_system", "external_id"],
        schema="app",
    )

    _add_source_columns("demand_todo_items")
    op.create_unique_constraint(
        "uq_demand_todo_external",
        "demand_todo_items",
        ["demand_id", "source_system", "external_id"],
        schema="app",
    )

    op.alter_column("demand_files", "storage_bucket", nullable=True, schema="app")
    op.alter_column("demand_files", "storage_path", nullable=True, schema="app")
    _add_source_columns("demand_files")
    op.add_column("demand_files", sa.Column("external_url", sa.Text()), schema="app")
    op.create_unique_constraint(
        "uq_demand_file_external",
        "demand_files",
        ["demand_id", "source_system", "external_id"],
        schema="app",
    )
    op.create_check_constraint(
        "ck_demand_file_location",
        "demand_files",
        "(storage_bucket IS NOT NULL AND storage_path IS NOT NULL) OR external_url IS NOT NULL",
        schema="app",
    )


def _drop_source_columns(table: str) -> None:
    op.drop_index(f"ix_{table}_import_batch_id", table_name=table, schema="app")
    op.drop_constraint(f"fk_{table}_import_batch", table, schema="app", type_="foreignkey")
    op.drop_column(table, "import_batch_id", schema="app")
    op.drop_column(table, "external_id", schema="app")
    op.drop_column(table, "source_system", schema="app")


def downgrade() -> None:
    op.drop_constraint("ck_demand_file_location", "demand_files", schema="app", type_="check")
    op.drop_constraint("uq_demand_file_external", "demand_files", schema="app", type_="unique")
    op.drop_column("demand_files", "external_url", schema="app")
    _drop_source_columns("demand_files")
    op.alter_column("demand_files", "storage_path", nullable=False, schema="app")
    op.alter_column("demand_files", "storage_bucket", nullable=False, schema="app")

    op.drop_constraint("uq_demand_todo_external", "demand_todo_items", schema="app", type_="unique")
    _drop_source_columns("demand_todo_items")

    op.drop_constraint("uq_demand_update_external", "demand_updates", schema="app", type_="unique")
    _drop_source_columns("demand_updates")

    op.drop_constraint("uq_comment_external", "comments", schema="app", type_="unique")
    _drop_source_columns("comments")
