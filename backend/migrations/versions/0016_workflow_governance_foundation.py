"""Fundacao aditiva para templates versionados e governanca de workflow."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_workflow_governance"
down_revision: str | None = "0015_data_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_roles", sa.Column("code", sa.String(60)), schema="app")
    op.execute(
        """
        UPDATE app.job_roles
        SET code = 'LEGACY_' || upper(substr(replace(id::text, '-', ''), 1, 12))
        WHERE code IS NULL
        """
    )
    op.alter_column("job_roles", "code", nullable=False, schema="app")
    op.create_unique_constraint(
        "uq_job_role_org_code", "job_roles", ["organization_id", "code"], schema="app"
    )

    op.create_table(
        "member_role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "membership_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.memberships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.job_roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "membership_id", "job_role_id", name="uq_member_role_assignment_membership_role"
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 1000", name="ck_member_role_priority"),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_member_role_validity",
        ),
        schema="app",
    )
    for column in ("organization_id", "membership_id", "job_role_id"):
        op.create_index(
            f"ix_member_role_assignments_{column}",
            "member_role_assignments",
            [column],
            schema="app",
        )

    op.add_column(
        "workflows",
        sa.Column("lifecycle_state", sa.String(20), nullable=False, server_default="PUBLISHED"),
        schema="app",
    )
    op.add_column(
        "workflows",
        sa.Column("time_basis", sa.String(20), nullable=False, server_default="ELAPSED"),
        schema="app",
    )
    op.add_column("workflows", sa.Column("published_at", sa.DateTime(timezone=True)), schema="app")
    op.execute("UPDATE app.workflows SET published_at = created_at WHERE published_at IS NULL")
    op.create_check_constraint(
        "ck_workflow_lifecycle_state",
        "workflows",
        "lifecycle_state IN ('DRAFT', 'PUBLISHED', 'RETIRED')",
        schema="app",
    )
    op.create_check_constraint(
        "ck_workflow_time_basis",
        "workflows",
        "time_basis IN ('ELAPSED', 'BUSINESS')",
        schema="app",
    )

    op.add_column(
        "workflow_stages",
        sa.Column(
            "owner_role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.job_roles.id", ondelete="RESTRICT"),
        ),
        schema="app",
    )
    op.add_column(
        "workflow_stages",
        sa.Column(
            "fallback_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        schema="app",
    )
    op.add_column("workflow_stages", sa.Column("sla_hours", sa.Integer()), schema="app")
    op.add_column("workflow_stages", sa.Column("acceptance_rule", sa.Text()), schema="app")
    op.add_column(
        "workflow_stages",
        sa.Column(
            "condition_rule",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_workflow_stages_owner_role_id",
        "workflow_stages",
        ["owner_role_id"],
        schema="app",
    )
    op.create_index(
        "ix_workflow_stages_fallback_user_id",
        "workflow_stages",
        ["fallback_user_id"],
        schema="app",
    )
    op.create_check_constraint(
        "ck_workflow_stage_sla_hours",
        "workflow_stages",
        "sla_hours IS NULL OR sla_hours > 0",
        schema="app",
    )

    op.create_table(
        "briefing_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demand_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("organization_id", "code", name="uq_briefing_template_org_code"),
        sa.UniqueConstraint("category_id", name="uq_briefing_template_category"),
        schema="app",
    )
    op.create_index(
        "ix_briefing_templates_organization_id",
        "briefing_templates",
        ["organization_id"],
        schema="app",
    )
    op.create_index(
        "ix_briefing_templates_category_id",
        "briefing_templates",
        ["category_id"],
        schema="app",
    )

    op.create_table(
        "briefing_template_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.briefing_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("template_id", "version", name="uq_briefing_template_version"),
        sa.CheckConstraint(
            "state IN ('DRAFT', 'PUBLISHED', 'RETIRED')",
            name="ck_briefing_template_version_state",
        ),
        schema="app",
    )
    for column in ("organization_id", "template_id"):
        op.create_index(
            f"ix_briefing_template_versions_{column}",
            "briefing_template_versions",
            [column],
            schema="app",
        )

    op.create_table(
        "category_template_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demand_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workflow_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.workflow_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "briefing_template_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.briefing_template_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        sa.Column(
            "activated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_category_template_binding_validity",
        ),
        schema="app",
    )
    for column in (
        "organization_id",
        "category_id",
        "workflow_version_id",
        "briefing_template_version_id",
    ):
        op.create_index(
            f"ix_category_template_bindings_{column}",
            "category_template_bindings",
            [column],
            schema="app",
        )
    op.create_index(
        "ix_category_binding_current",
        "category_template_bindings",
        ["category_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("effective_until IS NULL"),
    )

    op.add_column(
        "demands",
        sa.Column("operational_state", sa.String(20), nullable=False, server_default="ACTIVE"),
        schema="app",
    )
    op.add_column(
        "demands",
        sa.Column(
            "requester_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        schema="app",
    )
    op.add_column(
        "demands",
        sa.Column(
            "technical_specialist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        schema="app",
    )
    op.add_column(
        "demands",
        sa.Column("approval_risk", sa.String(10), nullable=False, server_default="A1"),
        schema="app",
    )
    op.add_column(
        "demands",
        sa.Column(
            "briefing_template_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.briefing_template_versions.id", ondelete="RESTRICT"),
        ),
        schema="app",
    )
    op.add_column(
        "demands",
        sa.Column(
            "category_template_binding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.category_template_bindings.id", ondelete="RESTRICT"),
        ),
        schema="app",
    )
    op.execute("UPDATE app.demands SET operational_state = 'BLOCKED' WHERE status = 'BLOCKED'")
    op.create_check_constraint(
        "ck_demand_operational_state",
        "demands",
        "operational_state IN ('ACTIVE', 'BLOCKED', 'PAUSED')",
        schema="app",
    )
    op.create_check_constraint(
        "ck_demand_approval_risk",
        "demands",
        "approval_risk IN ('A1', 'A2', 'A3')",
        schema="app",
    )
    for column in (
        "requester_id",
        "technical_specialist_id",
        "briefing_template_version_id",
        "category_template_binding_id",
    ):
        op.create_index(f"ix_demands_{column}", "demands", [column], schema="app")

    op.create_table(
        "demand_stage_visits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "demand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.workflow_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workflow_stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.workflow_stages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("visit_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column(
            "assignee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "entered_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "left_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text()),
        sa.Column("acceptance_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source", sa.String(30), nullable=False, server_default="workflow"),
        sa.Column("inferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("demand_id", "visit_number", name="uq_demand_stage_visit_number"),
        sa.CheckConstraint("visit_number > 0", name="ck_demand_stage_visit_number"),
        schema="app",
    )
    for column in (
        "organization_id",
        "demand_id",
        "workflow_version_id",
        "workflow_stage_id",
        "assignee_id",
    ):
        op.create_index(
            f"ix_demand_stage_visits_{column}",
            "demand_stage_visits",
            [column],
            schema="app",
        )

    op.create_table(
        "demand_state_intervals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "demand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.demands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "started_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "ended_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column("source", sa.String(30), nullable=False, server_default="interface"),
        sa.Column("inferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "state IN ('ACTIVE', 'BLOCKED', 'PAUSED')", name="ck_demand_state_interval_state"
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at", name="ck_demand_state_interval_time"
        ),
        schema="app",
    )
    for column in ("organization_id", "demand_id"):
        op.create_index(
            f"ix_demand_state_intervals_{column}",
            "demand_state_intervals",
            [column],
            schema="app",
        )
    op.create_index(
        "ix_demand_state_interval_open",
        "demand_state_intervals",
        ["demand_id", "state"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.execute(
        """
        INSERT INTO app.demand_stage_visits
            (id, organization_id, demand_id, workflow_version_id, workflow_stage_id,
             visit_number, action, assignee_id, entered_by, entered_at,
             acceptance_snapshot, source, inferred, created_at)
        SELECT gen_random_uuid(), demand.organization_id, demand.id, demand.workflow_version_id,
               demand.current_stage_id, 1, 'IMPORT', demand.current_assignee_id,
               demand.created_by, COALESCE(instance.entered_at, demand.created_at),
               '{}'::jsonb, 'legacy_backfill', true, now()
        FROM app.demands demand
        LEFT JOIN app.demand_stage_instances instance
          ON instance.demand_id = demand.id
         AND instance.workflow_version_id = demand.workflow_version_id
         AND instance.workflow_stage_id = demand.current_stage_id
        WHERE demand.workflow_version_id IS NOT NULL
          AND demand.current_stage_id IS NOT NULL
        """
    )

    brand_rows = [
        ("Gomide Contabilidade", "Gomide", "GOMIDE_CONTABILIDADE", "#0F766E"),
        ("Expert Consultoria", "Expert", "EXPERT_CONSULTORIA", "#2563EB"),
        ("Imposto no Bolso", "Imposto", "IMPOSTO_NO_BOLSO", "#D97706"),
        ("EloFiscal", "EloFiscal", "ELOFISCAL", "#7C3AED"),
        ("Eclusa", "Eclusa", "ECLUSA", "#0891B2"),
        (
            "Gomide e Oliveira Advogados",
            "Gomide e Oliveira",
            "GOMIDE_OLIVEIRA_ADVOGADOS",
            "#334155",
        ),
        ("Rafael Oliveira", "Rafael", "RAFAEL_OLIVEIRA", "#DC2626"),
        ("Anderson Nunes", "Anderson", "ANDERSON_NUNES", "#16A34A"),
        ("Retributária", "Retributária", "RETRIBUTARIA", "#9333EA"),
    ]
    for name, short_name, code, color in brand_rows:
        op.execute(
            sa.text(
                """
                INSERT INTO app.companies
                    (id, organization_id, name, short_name, code, color, description,
                     active, revision, created_at, updated_at)
                SELECT gen_random_uuid(), organization.id, :name, :short_name, :code, :color,
                       'Marca cadastrada pela configuração operacional de 15/10/2026.',
                       true, 1, now(), now()
                FROM app.organizations organization
                ON CONFLICT DO NOTHING
                """
            ).bindparams(name=name, short_name=short_name, code=code, color=color)
        )

    role_rows = [
        ("STRATEGY_APPROVAL", "Estratégia, aprovação e priorização"),
        ("COPY_CONTENT", "Copy, redação e conteúdo"),
        ("EDITORIAL_PUBLICATION", "Planejamento editorial e publicação"),
        ("DESIGN_AUDIOVISUAL", "Design, edição e audiovisual"),
        ("TECH_AUTOMATION", "Tecnologia e automações"),
        ("COMMERCIAL_RELATIONSHIP", "Comercial e relacionamento"),
        ("LOGISTICS_SUPPLIERS", "Logística e fornecedores"),
        ("TECHNICAL_SPECIALIST", "Especialista técnico"),
        ("ACCOUNTING_VALIDATION", "Validação contábil"),
        ("FISCAL_VALIDATION", "Validação fiscal"),
        ("FISCON_VALIDATION", "Validação FisCon"),
        ("CORPORATE_VALIDATION", "Validação societária"),
        ("HR_PAYROLL_VALIDATION", "Validação departamento pessoal"),
        ("TAX_STRATEGIC_VALIDATION", "Validação tributária e estratégica"),
    ]
    for code, name in role_rows:
        op.execute(
            sa.text(
                """
                INSERT INTO app.job_roles
                    (id, organization_id, code, name, description, active, revision)
                SELECT gen_random_uuid(), organization.id, :code, :name,
                       'Papel operacional configurável; associações de usuários são administradas separadamente.',
                       true, 1
                FROM app.organizations organization
                ON CONFLICT DO NOTHING
                """
            ).bindparams(code=code, name=name)
        )


def downgrade() -> None:
    op.drop_table("demand_state_intervals", schema="app")
    op.drop_table("demand_stage_visits", schema="app")

    for column in (
        "category_template_binding_id",
        "briefing_template_version_id",
        "technical_specialist_id",
        "requester_id",
        "approval_risk",
        "operational_state",
    ):
        op.drop_column("demands", column, schema="app")

    op.drop_table("category_template_bindings", schema="app")
    op.drop_table("briefing_template_versions", schema="app")
    op.drop_table("briefing_templates", schema="app")

    for constraint in ("ck_workflow_stage_sla_hours",):
        op.drop_constraint(constraint, "workflow_stages", schema="app", type_="check")
    for column in (
        "condition_rule",
        "acceptance_rule",
        "sla_hours",
        "fallback_user_id",
        "owner_role_id",
    ):
        op.drop_column("workflow_stages", column, schema="app")

    op.drop_constraint("ck_workflow_time_basis", "workflows", schema="app", type_="check")
    op.drop_constraint("ck_workflow_lifecycle_state", "workflows", schema="app", type_="check")
    for column in ("published_at", "time_basis", "lifecycle_state"):
        op.drop_column("workflows", column, schema="app")

    op.drop_table("member_role_assignments", schema="app")
    op.drop_constraint("uq_job_role_org_code", "job_roles", schema="app", type_="unique")
    op.drop_column("job_roles", "code", schema="app")
