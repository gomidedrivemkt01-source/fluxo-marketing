"""Comentarios, historico de edicao e acompanhantes da demanda."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_collaboration_activity"
down_revision: str | None = "0006_stage_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "demand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("char_length(trim(content)) > 0", name="ck_comment_content_not_blank"),
        schema="app",
    )
    op.create_index("ix_comments_demand_id", "comments", ["demand_id"], schema="app")
    op.create_index("ix_comments_author_id", "comments", ["author_id"], schema="app")
    op.create_index(
        "ix_comments_demand_created", "comments", ["demand_id", "created_at"], schema="app"
    )

    op.create_table(
        "comment_edits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "comment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.comments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "edited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("previous_content", sa.Text(), nullable=False),
        sa.Column("new_content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="app",
    )
    op.create_index("ix_comment_edits_comment_id", "comment_edits", ["comment_id"], schema="app")
    op.create_index(
        "ix_comment_edits_comment_created",
        "comment_edits",
        ["comment_id", "created_at"],
        schema="app",
    )

    op.create_table(
        "demand_watchers",
        sa.Column(
            "demand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demands.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "added_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="app",
    )
    op.create_index(
        "ix_demand_watchers_profile", "demand_watchers", ["user_profile_id"], schema="app"
    )
    op.execute(
        "INSERT INTO app.demand_updates "
        "(id, demand_id, created_by, kind, summary, payload, created_at) "
        "SELECT gen_random_uuid(), demand.id, demand.created_by, 'DEMAND_CREATED', "
        "'Demanda criada.', jsonb_build_object('publicId', demand.public_id, "
        "'source', demand.source), demand.created_at "
        "FROM app.demands AS demand "
        "WHERE NOT EXISTS ("
        "SELECT 1 FROM app.demand_updates AS update_event "
        "WHERE update_event.demand_id = demand.id AND update_event.kind = 'DEMAND_CREATED'"
        ")"
    )


def downgrade() -> None:
    op.execute("DELETE FROM app.demand_updates WHERE kind = 'DEMAND_CREATED'")
    op.drop_index("ix_demand_watchers_profile", table_name="demand_watchers", schema="app")
    op.drop_table("demand_watchers", schema="app")
    op.drop_index(
        "ix_comment_edits_comment_created", table_name="comment_edits", schema="app"
    )
    op.drop_index("ix_comment_edits_comment_id", table_name="comment_edits", schema="app")
    op.drop_table("comment_edits", schema="app")
    op.drop_index("ix_comments_demand_created", table_name="comments", schema="app")
    op.drop_index("ix_comments_author_id", table_name="comments", schema="app")
    op.drop_index("ix_comments_demand_id", table_name="comments", schema="app")
    op.drop_table("comments", schema="app")
