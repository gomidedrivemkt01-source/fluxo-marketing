"""Foto de perfil armazenada no banco para o MVP."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_profile_avatar"
down_revision: str | None = "0002_demands_daily_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("avatar_data", sa.LargeBinary()), schema="app")
    op.add_column(
        "user_profiles", sa.Column("avatar_content_type", sa.String(80)), schema="app"
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "avatar_content_type", schema="app")
    op.drop_column("user_profiles", "avatar_data", schema="app")
