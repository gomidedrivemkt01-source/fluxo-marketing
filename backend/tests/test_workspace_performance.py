import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.api import workspace
from app.api.demands import demands_out
from app.api.users import ProfileOut, UserOptionOut


def test_workspace_bootstrap_combines_common_screen_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid.uuid4()
    category_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    stage_id = uuid.uuid4()
    company = SimpleNamespace(
        id=company_id,
        name="Gomide",
        short_name="Gomide",
        code="GOMIDE",
        color="#155E75",
        description=None,
        active=True,
        revision=1,
    )
    category = SimpleNamespace(
        id=category_id,
        name="Vídeo",
        code="VIDEO",
        color="#475569",
        default_workflow_id=workflow_id,
        active=True,
        revision=1,
    )
    workflow_item = SimpleNamespace(
        id=workflow_id,
        name="Vídeo",
        code="VIDEO",
        description=None,
        is_default=False,
        lifecycle_state="PUBLISHED",
        time_basis="ELAPSED",
        published_at=None,
        active=True,
        revision=1,
    )
    stage = SimpleNamespace(
        id=stage_id,
        workflow_id=workflow_id,
        name="Briefing",
        code="BRIEFING",
        color="#475569",
        position=1,
        default_assignee_id=None,
        owner_role_id=None,
        fallback_user_id=None,
        expected_duration_hours=None,
        sla_hours=None,
        acceptance_rule=None,
        condition_rule={},
        active=True,
        revision=1,
    )
    profile = ProfileOut(
        profileId=uuid.uuid4(),
        name="Admin",
        email="admin@example.com",
        timezone="America/Sao_Paulo",
        role="admin",
        revision=1,
        avatarUrl=None,
        preferences={},
    )
    people = [UserOptionOut(id=profile.profile_id, name=profile.name, avatarUrl=None)]

    monkeypatch.setattr(workspace, "list_companies", MagicMock(return_value=[company]))
    monkeypatch.setattr(workspace, "list_categories", MagicMock(return_value=[category]))
    workflows_mock = MagicMock(return_value=[workflow_item])
    stages_mock = MagicMock(return_value=[stage])
    monkeypatch.setattr(workspace, "list_workflows", workflows_mock)
    monkeypatch.setattr(workspace, "list_workflow_stages", stages_mock)
    monkeypatch.setattr(workspace, "list_user_options", MagicMock(return_value=people))
    monkeypatch.setattr(workspace, "list_demands", MagicMock(return_value=[]))
    monkeypatch.setattr(workspace, "get_my_profile", MagicMock(return_value=profile))

    result = workspace.workspace_bootstrap(MagicMock(), MagicMock(spec=Session))

    assert result.companies[0].short_name == "Gomide"
    assert result.categories[0].default_workflow_id == workflow_id
    assert result.profile.email == "admin@example.com"
    workflows_mock.assert_called_once_with(
        include_inactive=False,
        include_draft=False,
        principal=ANY,
        db=ANY,
    )
    stages_mock.assert_called_once_with(
        include_inactive=False,
        include_draft=False,
        workflow_id=None,
        all_workflows=True,
        principal=ANY,
        db=ANY,
    )


def test_demands_out_uses_fixed_number_of_related_queries() -> None:
    now = datetime.now(UTC)
    company_id = uuid.uuid4()
    category_id = uuid.uuid4()
    assignee_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    stage_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    version_id = uuid.uuid4()
    demand = SimpleNamespace(
        id=uuid.uuid4(),
        public_id="DMD-2026-000001",
        title="Demanda",
        description=None,
        primary_company_id=company_id,
        category_id=category_id,
        current_assignee_id=assignee_id,
        created_by=creator_id,
        current_stage_id=stage_id,
        workflow_id=workflow_id,
        workflow_version_id=version_id,
        status="IN_PROGRESS",
        priority="NORMAL",
        deadline_at=None,
        forecast_at=None,
        expected_effort_minutes=None,
        revision=1,
        created_at=now,
    )
    cover_id = uuid.uuid4()
    related = [
        [SimpleNamespace(id=company_id, name="Gomide", color="#155E75")],
        [SimpleNamespace(id=category_id, name="Vídeo", color="#475569")],
        [
            SimpleNamespace(
                id=assignee_id,
                full_name="Responsável",
                avatar_path=None,
                revision=1,
            ),
            SimpleNamespace(id=creator_id, full_name="Criador"),
        ],
        [
            SimpleNamespace(
                id=stage_id,
                name="Briefing",
                code="BRIEFING",
                color="#475569",
                position=1,
            )
        ],
        [SimpleNamespace(id=workflow_id, name="Vídeo")],
        [
            SimpleNamespace(
                id=version_id,
                version=1,
                definition={
                    "stages": [
                        {
                            "id": str(stage_id),
                            "name": "Briefing",
                            "code": "BRIEFING",
                            "color": "#475569",
                            "position": 1,
                        }
                    ]
                },
            )
        ],
        [SimpleNamespace(id=cover_id, demand_id=demand.id)],
    ]
    db = MagicMock(spec=Session)
    db.scalars.side_effect = related

    result = demands_out(db, [demand, demand])

    assert db.scalars.call_count == 7
    assert len(result) == 2
    assert result[0].company_name == "Gomide"
    assert result[0].assignee_name == "Responsável"
    assert result[0].stage_name == "Briefing"
    assert result[0].cover_image_url == f"/api/v1/demands/{demand.id}/files/{cover_id}/preview"
