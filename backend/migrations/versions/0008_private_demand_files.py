"""Arquivos privados vinculados às demandas."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_private_demand_files"
down_revision: str | None = "0007_collaboration_activity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUCKET_ID = "demand-files"


def upgrade() -> None:
    op.create_table(
        "demand_files",
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
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.user_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_bucket", sa.String(length=100), nullable=False),
        sa.Column("storage_path", sa.String(length=700), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "storage_bucket", "storage_path", name="uq_demand_file_storage_path"
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_demand_file_size_positive"),
        sa.CheckConstraint("char_length(sha256) = 64", name="ck_demand_file_sha256_length"),
        schema="app",
    )
    op.create_index(
        "ix_demand_files_organization_id", "demand_files", ["organization_id"], schema="app"
    )
    op.create_index("ix_demand_files_demand_id", "demand_files", ["demand_id"], schema="app")
    op.create_index(
        "ix_demand_files_uploaded_by", "demand_files", ["uploaded_by"], schema="app"
    )
    op.create_index(
        "ix_demand_files_demand_created",
        "demand_files",
        ["demand_id", "created_at"],
        schema="app",
    )

    op.execute(
        """
        DO $do$
        BEGIN
            IF to_regclass('storage.buckets') IS NULL
               OR to_regclass('storage.objects') IS NULL THEN
                RETURN;
            END IF;

            EXECUTE $ddl$
                CREATE OR REPLACE FUNCTION app.storage_can_upload_demand_file(object_name text)
                RETURNS boolean
                LANGUAGE sql
                STABLE
                SECURITY DEFINER
                SET search_path = ''
                AS $function$
                    SELECT EXISTS (
                        SELECT 1
                        FROM app.user_profiles profile
                        JOIN app.memberships membership
                          ON membership.user_profile_id = profile.id
                        JOIN app.permission_roles role
                          ON role.id = membership.permission_role_id
                        JOIN app.demands demand
                          ON demand.organization_id = membership.organization_id
                        WHERE profile.auth_user_id = auth.uid()
                          AND membership.status = 'ACTIVE'
                          AND role.permissions ?| ARRAY['*', 'demands:write', 'demands:work']
                          AND demand.deleted_at IS NULL
                          AND membership.organization_id::text =
                              (storage.foldername(object_name))[1]
                          AND demand.id::text = (storage.foldername(object_name))[2]
                    )
                $function$
            $ddl$;
            EXECUTE $ddl$
                CREATE OR REPLACE FUNCTION app.storage_can_read_demand_file(object_name text)
                RETURNS boolean
                LANGUAGE sql
                STABLE
                SECURITY DEFINER
                SET search_path = ''
                AS $function$
                    SELECT EXISTS (
                        SELECT 1
                        FROM app.user_profiles profile
                        JOIN app.memberships membership
                          ON membership.user_profile_id = profile.id
                        JOIN app.permission_roles role
                          ON role.id = membership.permission_role_id
                        JOIN app.demand_files demand_file
                          ON demand_file.organization_id = membership.organization_id
                        JOIN app.demands demand ON demand.id = demand_file.demand_id
                        WHERE profile.auth_user_id = auth.uid()
                          AND membership.status = 'ACTIVE'
                          AND role.permissions ?| ARRAY['*', 'demands:read']
                          AND demand.deleted_at IS NULL
                          AND demand_file.deleted_at IS NULL
                          AND demand_file.storage_bucket = 'demand-files'
                          AND demand_file.storage_path = object_name
                          AND membership.organization_id::text =
                              (storage.foldername(object_name))[1]
                    )
                $function$
            $ddl$;
            EXECUTE $ddl$
                CREATE OR REPLACE FUNCTION app.storage_can_delete_demand_file(object_name text)
                RETURNS boolean
                LANGUAGE sql
                STABLE
                SECURITY DEFINER
                SET search_path = ''
                AS $function$
                    SELECT EXISTS (
                        SELECT 1
                        FROM app.user_profiles profile
                        JOIN app.memberships membership
                          ON membership.user_profile_id = profile.id
                        JOIN app.permission_roles role
                          ON role.id = membership.permission_role_id
                        JOIN app.demands demand
                          ON demand.organization_id = membership.organization_id
                        WHERE profile.auth_user_id = auth.uid()
                          AND membership.status = 'ACTIVE'
                          AND role.permissions ?| ARRAY['*', 'demands:write', 'demands:work']
                          AND demand.deleted_at IS NULL
                          AND membership.organization_id::text =
                              (storage.foldername(object_name))[1]
                          AND demand.id::text = (storage.foldername(object_name))[2]
                    )
                $function$
            $ddl$;

            EXECUTE 'REVOKE ALL ON FUNCTION app.storage_can_upload_demand_file(text) FROM PUBLIC';
            EXECUTE 'REVOKE ALL ON FUNCTION app.storage_can_read_demand_file(text) FROM PUBLIC';
            EXECUTE 'REVOKE ALL ON FUNCTION app.storage_can_delete_demand_file(text) FROM PUBLIC';
            EXECUTE 'GRANT EXECUTE ON FUNCTION app.storage_can_upload_demand_file(text) TO authenticated';
            EXECUTE 'GRANT EXECUTE ON FUNCTION app.storage_can_read_demand_file(text) TO authenticated';
            EXECUTE 'GRANT EXECUTE ON FUNCTION app.storage_can_delete_demand_file(text) TO authenticated';
            EXECUTE 'GRANT USAGE ON SCHEMA app TO authenticated';

            INSERT INTO storage.buckets
                (id, name, public, file_size_limit, allowed_mime_types)
            VALUES
                ('demand-files', 'demand-files', false, 26214400, ARRAY[
                    'application/pdf',
                    'image/png', 'image/jpeg', 'image/webp', 'image/gif',
                    'text/plain', 'text/csv',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    'audio/mpeg', 'audio/wav', 'audio/mp4',
                    'video/mp4', 'video/webm', 'video/quicktime'
                ]::text[])
            ON CONFLICT (id) DO UPDATE SET
                public = false,
                file_size_limit = EXCLUDED.file_size_limit,
                allowed_mime_types = EXCLUDED.allowed_mime_types;

            DROP POLICY IF EXISTS "demand_files_insert" ON storage.objects;
            DROP POLICY IF EXISTS "demand_files_select" ON storage.objects;
            DROP POLICY IF EXISTS "demand_files_delete_own" ON storage.objects;

            CREATE POLICY "demand_files_insert"
            ON storage.objects FOR INSERT TO authenticated
            WITH CHECK (
                bucket_id = 'demand-files'
                AND app.storage_can_upload_demand_file(name)
            );

            CREATE POLICY "demand_files_select"
            ON storage.objects FOR SELECT TO authenticated
            USING (
                bucket_id = 'demand-files'
                AND app.storage_can_read_demand_file(name)
            );

            CREATE POLICY "demand_files_delete_own"
            ON storage.objects FOR DELETE TO authenticated
            USING (
                bucket_id = 'demand-files'
                AND owner_id = auth.uid()::text
                AND app.storage_can_delete_demand_file(name)
            );
        END $do$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('storage.objects') IS NULL THEN
                RETURN;
            END IF;
            DROP POLICY IF EXISTS "demand_files_delete_own" ON storage.objects;
            DROP POLICY IF EXISTS "demand_files_select" ON storage.objects;
            DROP POLICY IF EXISTS "demand_files_insert" ON storage.objects;
        END $$;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS app.storage_can_delete_demand_file(text)")
    op.execute("DROP FUNCTION IF EXISTS app.storage_can_read_demand_file(text)")
    op.execute("DROP FUNCTION IF EXISTS app.storage_can_upload_demand_file(text)")
    op.drop_index(
        "ix_demand_files_demand_created", table_name="demand_files", schema="app"
    )
    op.drop_index("ix_demand_files_uploaded_by", table_name="demand_files", schema="app")
    op.drop_index("ix_demand_files_demand_id", table_name="demand_files", schema="app")
    op.drop_index("ix_demand_files_organization_id", table_name="demand_files", schema="app")
    op.drop_table("demand_files", schema="app")
