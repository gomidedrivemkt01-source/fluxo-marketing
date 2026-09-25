"""Etapas compartilhadas, responsáveis e preferências individuais de visualização."""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_shared_workflow"
down_revision: str | None = "0003_profile_avatar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_STAGES = [
    ("ENTRADA", "Entrada", "#64748B"),
    ("BRIEFING", "Briefing", "#0F766E"),
    ("PLANEJAMENTO", "Planejamento", "#2563EB"),
    ("PRODUCAO", "Produção", "#7C3AED"),
    ("REVISAO", "Revisão", "#D97706"),
    ("APROVACAO", "Aprovação", "#DB2777"),
    ("PUBLICACAO", "Publicação / entrega", "#0891B2"),
    ("CONCLUIDA", "Concluída", "#15803D"),
]


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "workspace_preferences",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        schema="app",
    )
    op.create_table(
        "workflow_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("organization_id", "code", name="uq_workflow_stage_org_code"),
        schema="app",
    )
    op.create_index(
        "ix_workflow_stages_organization_id",
        "workflow_stages",
        ["organization_id"],
        schema="app",
    )
    op.add_column(
        "demands",
        sa.Column(
            "current_stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.workflow_stages.id", ondelete="RESTRICT"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_demands_current_stage_id", "demands", ["current_stage_id"], schema="app"
    )

    connection = op.get_bind()
    organization_ids = list(
        connection.execute(sa.text("SELECT id FROM app.organizations")).scalars()
    )
    for organization_id in organization_ids:
        first_stage_id: uuid.UUID | None = None
        for position, (code, name, color) in enumerate(DEFAULT_STAGES, start=1):
            stage_id = uuid.uuid4()
            first_stage_id = first_stage_id or stage_id
            connection.execute(
                sa.text(
                    "INSERT INTO app.workflow_stages "
                    "(id, organization_id, name, code, color, position, active, revision) "
                    "VALUES (:id, :organization_id, :name, :code, :color, :position, true, 1)"
                ),
                {
                    "id": stage_id,
                    "organization_id": organization_id,
                    "name": name,
                    "code": code,
                    "color": color,
                    "position": position,
                },
            )
        connection.execute(
            sa.text(
                "UPDATE app.demands SET current_stage_id = :stage_id "
                "WHERE organization_id = :organization_id AND current_stage_id IS NULL"
            ),
            {"stage_id": first_stage_id, "organization_id": organization_id},
        )


def downgrade() -> None:
    op.drop_index("ix_demands_current_stage_id", table_name="demands", schema="app")
    op.drop_column("demands", "current_stage_id", schema="app")
    op.drop_index(
        "ix_workflow_stages_organization_id", table_name="workflow_stages", schema="app"
    )
    op.drop_table("workflow_stages", schema="app")
    op.drop_column("user_profiles", "workspace_preferences", schema="app")
