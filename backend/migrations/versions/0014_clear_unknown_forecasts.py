"""Remove previsoes artificiais de etapas sem duracao configurada."""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_clear_unknown_forecasts"
down_revision: str | None = "0013_demand_stage_instances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE app.demand_stage_instances AS instance
        SET forecast_at = NULL, updated_at = now()
        FROM app.workflow_versions AS version,
             LATERAL jsonb_array_elements(version.definition->'stages') AS stage(item)
        WHERE version.id = instance.workflow_version_id
          AND (stage.item->>'id')::uuid = instance.workflow_stage_id
          AND stage.item->>'expectedDurationHours' IS NULL
          AND instance.state = 'upcoming'
        """
    )


def downgrade() -> None:
    pass
