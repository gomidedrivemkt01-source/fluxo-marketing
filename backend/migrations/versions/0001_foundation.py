"""Fase 1: organização, acesso, cadastros, sessões e auditoria."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

organization_id = "00000000-0000-4000-8000-000000000001"
role_ids = {
    "admin": "00000000-0000-4000-8000-000000000010",
    "coordinator": "00000000-0000-4000-8000-000000000011",
    "collaborator": "00000000-0000-4000-8000-000000000012",
    "viewer": "00000000-0000-4000-8000-000000000013",
}


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute(
        "CREATE TYPE app.membership_status AS ENUM "
        "('PENDING_APPROVAL', 'ACTIVE', 'SUSPENDED')"
    )
    membership_status = postgresql.ENUM(
        "PENDING_APPROVAL",
        "ACTIVE",
        "SUSPENDED",
        name="membership_status",
        schema="app",
        create_type=False,
    )
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="app",
    )
    op.create_table(
        "permission_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("permissions", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("system_role", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.UniqueConstraint("organization_id", "code", name="uq_permission_role_org_code"),
        schema="app",
    )
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("auth_user_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("avatar_path", sa.String(500)),
        sa.Column("timezone", sa.String(80), server_default="America/Sao_Paulo", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="app",
    )
    op.create_index(
        "ix_user_profiles_auth_user_id", "user_profiles", ["auth_user_id"], schema="app"
    )
    op.create_index("ix_user_profiles_email", "user_profiles", ["email"], schema="app")
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "permission_role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.permission_roles.id", ondelete="RESTRICT"),
        ),
        sa.Column("status", membership_status, nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("suspended_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("organization_id", "user_profile_id", name="uq_membership_org_user"),
        schema="app",
    )
    op.create_index(
        "ix_memberships_organization_id", "memberships", ["organization_id"], schema="app"
    )
    op.create_index(
        "ix_memberships_user_profile_id", "memberships", ["user_profile_id"], schema="app"
    )
    op.create_table(
        "job_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_job_role_org_name"),
        schema="app",
    )
    op.create_index("ix_job_roles_organization_id", "job_roles", ["organization_id"], schema="app")
    op.create_table(
        "member_job_roles",
        sa.Column(
            "membership_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.memberships.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "job_role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.job_roles.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        schema="app",
    )
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("short_name", sa.String(80), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("color", sa.String(7), server_default="#155E75", nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("organization_id", "name", name="uq_company_org_name"),
        sa.UniqueConstraint("organization_id", "code", name="uq_company_org_code"),
        schema="app",
    )
    op.create_index("ix_companies_organization_id", "companies", ["organization_id"], schema="app")
    op.create_table(
        "demand_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("color", sa.String(7), server_default="#475569", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_category_org_name"),
        sa.UniqueConstraint("organization_id", "code", name="uq_category_org_code"),
        schema="app",
    )
    op.create_index(
        "ix_categories_organization_id", "demand_categories", ["organization_id"], schema="app"
    )
    op.create_table(
        "app_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("access_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("refresh_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="app",
    )
    op.create_index(
        "ix_session_active_token", "app_sessions", ["token_hash"], unique=True, schema="app"
    )
    op.create_index(
        "ix_app_sessions_user_profile_id", "app_sessions", ["user_profile_id"], schema="app"
    )
    op.create_index("ix_app_sessions_expires_at", "app_sessions", ["expires_at"], schema="app")
    op.create_index(
        "ix_app_sessions_idle_expires_at", "app_sessions", ["idle_expires_at"], schema="app"
    )
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("source", sa.String(30), server_default="interface", nullable=False),
        sa.Column("request_id", sa.String(80)),
        sa.Column("metadata_json", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="app",
    )
    op.create_index(
        "ix_audit_org_created", "audit_events", ["organization_id", "created_at"], schema="app"
    )
    op.create_index(
        "ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"], schema="app"
    )
    op.create_table(
        "privacy_notice_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(30), nullable=False, unique=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        schema="app",
    )
    op.create_table(
        "privacy_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "notice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.privacy_notice_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_profile_id", "notice_id", name="uq_user_notice"),
        schema="app",
    )

    op.execute(
        sa.text(
            "INSERT INTO app.organizations (id, name, slug) "
            "VALUES (CAST(:id AS uuid), 'Marketing', 'marketing')"
        ).bindparams(id=organization_id)
    )
    role_rows = [
        (role_ids["admin"], "admin", "Administrador", '["*"]'),
        (
            role_ids["coordinator"],
            "coordinator",
            "Coordenador",
            '["users:read","catalog:read","catalog:write","audit:read","imports:write","demands:read","demands:write"]',
        ),
        (
            role_ids["collaborator"],
            "collaborator",
            "Colaborador",
            '["catalog:read","profile:write","demands:read","demands:work"]',
        ),
        (role_ids["viewer"], "viewer", "Visualizador", '["catalog:read","demands:read"]'),
    ]
    for role_id, code, name, permissions in role_rows:
        op.execute(
            sa.text(
                "INSERT INTO app.permission_roles (id, organization_id, code, name, permissions) "
                "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :code, :name, "
                "CAST(:permissions AS jsonb))"
            ).bindparams(
                id=role_id, org=organization_id, code=code, name=name, permissions=permissions
            )
        )
    categories = [
        ("Vídeo Reels", "VIDEO_REELS"),
        ("Vídeo YouTube", "VIDEO_YOUTUBE"),
        ("Carrossel", "CAROUSEL"),
        ("Blog", "BLOG"),
        ("Estático", "STATIC"),
        ("Story", "STORY"),
        ("Landing Page", "LANDING_PAGE"),
        ("Campanha", "CAMPAIGN"),
        ("Material Gráfico", "GRAPHIC_MATERIAL"),
        ("Endomarketing", "INTERNAL_MARKETING"),
        ("Automação", "AUTOMATION"),
        ("Evento", "EVENT"),
        ("Outro", "OTHER"),
    ]
    for name, code in categories:
        op.execute(
            sa.text(
                "INSERT INTO app.demand_categories (id, organization_id, name, code) "
                "VALUES (gen_random_uuid(), CAST(:org AS uuid), :name, :code)"
            ).bindparams(org=organization_id, name=name, code=code)
        )
    op.execute(
        "INSERT INTO app.privacy_notice_versions (id, version, published_at, active) "
        "VALUES ('00000000-0000-4000-8000-000000000020', 'draft-1', now(), true)"
    )


def downgrade() -> None:
    for table in [
        "privacy_acknowledgements",
        "privacy_notice_versions",
        "audit_events",
        "app_sessions",
        "demand_categories",
        "companies",
        "member_job_roles",
        "job_roles",
        "memberships",
        "user_profiles",
        "permission_roles",
        "organizations",
    ]:
        op.drop_table(table, schema="app")
    postgresql.ENUM(name="membership_status", schema="app").drop(op.get_bind(), checkfirst=True)
    op.execute("DROP SCHEMA IF EXISTS app")
