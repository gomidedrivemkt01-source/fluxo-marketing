import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.api.catalogs import (
    WorkflowInput,
    WorkflowStageReorder,
    WorkflowStageUpdate,
    reorder_workflow_stages,
    update_workflow_stage,
)
from app.api.demands import (
    apply_stage_defaults,
    get_demand_timeline,
    move_stage_plan,
    rebalance_stage_deadlines,
    stage_risk,
    validate_stage_handoff,
    version_stage,
    workflow_definition,
)
from app.api.errors import ApiError
from app.auth.service import Principal
from app.models import (
    AuditEvent,
    Demand,
    DemandStageInstance,
    DemandUpdate,
    Membership,
    MembershipStatus,
    PermissionRole,
    UserProfile,
    Workflow,
    WorkflowStage,
    WorkflowVersion,
)


def _principal() -> Principal:
    organization_id = uuid.uuid4()
    profile = UserProfile(
        id=uuid.uuid4(),
        auth_user_id=uuid.uuid4(),
        email="coordenacao@example.com",
        full_name="Coordenação",
    )
    membership = Membership(
        id=uuid.uuid4(),
        organization_id=organization_id,
        user_profile_id=profile.id,
        status=MembershipStatus.ACTIVE,
    )
    role = PermissionRole(
        id=uuid.uuid4(),
        organization_id=organization_id,
        code="coordinator",
        name="Coordenador",
        permissions=["catalog:write", "demands:read"],
    )
    return Principal(MagicMock(), profile, membership, role)


def test_reorder_updates_every_active_stage_and_registers_audit() -> None:
    principal = _principal()
    first = WorkflowStage(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        name="Entrada",
        code="ENTRADA",
        color="#64748B",
        position=1,
        revision=1,
        active=True,
    )
    second = WorkflowStage(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        name="Briefing",
        code="BRIEFING",
        color="#0F766E",
        position=2,
        revision=3,
        active=True,
    )
    db = MagicMock(spec=Session)
    db.scalars.return_value = iter([first, second])
    payload = WorkflowStageReorder(
        stages=[
            {"id": second.id, "expectedRevision": 3},
            {"id": first.id, "expectedRevision": 1},
        ]
    )

    result = reorder_workflow_stages(payload, principal, db)

    assert [stage.id for stage in result] == [second.id, first.id]
    assert (second.position, second.revision) == (1, 4)
    assert (first.position, first.revision) == (2, 2)
    audit = db.add.call_args.args[0]
    assert isinstance(audit, AuditEvent)
    assert audit.event_type == "WORKFLOW_STAGES_REORDERED"
    db.commit.assert_called_once()


def test_stage_with_demands_cannot_be_deactivated() -> None:
    principal = _principal()
    stage = WorkflowStage(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        name="Produção",
        code="PRODUCAO",
        color="#7C3AED",
        position=4,
        revision=2,
        active=True,
    )
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [stage, uuid.uuid4()]
    payload = WorkflowStageUpdate(
        name=stage.name,
        code=stage.code,
        color=stage.color,
        position=stage.position,
        expectedRevision=stage.revision,
        active=False,
    )

    with pytest.raises(ApiError) as caught:
        update_workflow_stage(stage.id, payload, principal, db)

    assert caught.value.code == "workflow_stage_in_use"
    db.commit.assert_not_called()


def test_stage_defaults_assign_owner_and_calculate_forecast() -> None:
    principal = _principal()
    assignee_id = uuid.uuid4()
    entered_at = datetime(2026, 9, 28, 12, tzinfo=UTC)
    stage = WorkflowStage(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        name="Produção",
        code="PRODUCAO",
        color="#7C3AED",
        position=4,
        default_assignee_id=assignee_id,
        expected_duration_hours=48,
        active=True,
    )
    demand = Demand(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        public_id="DMD-2026-000010",
        title="Vídeo institucional",
        status="WAITING_EXECUTION",
        priority="NORMAL",
        source="interface",
        revision=1,
        created_by=principal.profile.id,
    )

    apply_stage_defaults(demand, stage, entered_at=entered_at)

    assert demand.current_assignee_id == assignee_id
    assert demand.forecast_at == entered_at + timedelta(hours=48)


def test_workflow_definition_preserves_the_version_used_by_a_card() -> None:
    principal = _principal()
    stage = WorkflowStage(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        workflow_id=uuid.uuid4(),
        name="Edição",
        code="EDICAO",
        color="#2563EB",
        position=2,
        expected_duration_hours=24,
        active=True,
    )
    definition = workflow_definition([stage])
    version = WorkflowVersion(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        workflow_id=stage.workflow_id,
        version=1,
        definition=definition,
    )

    stage.name = "Pós-produção"
    stage.expected_duration_hours = 48
    frozen = version_stage(version, stage.id)

    assert frozen is not None
    assert frozen["name"] == "Edição"
    assert frozen["expectedDurationHours"] == 24


def test_demand_timeline_combines_history_with_the_frozen_future() -> None:
    principal = _principal()
    workflow_id = uuid.uuid4()
    version_id = uuid.uuid4()
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    third_id = uuid.uuid4()
    entered_second = datetime(2026, 9, 30, 12, tzinfo=UTC)
    demand = Demand(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        public_id="DMD-2026-000011",
        title="Campanha institucional",
        workflow_id=workflow_id,
        workflow_version_id=version_id,
        current_stage_id=second_id,
        forecast_at=entered_second + timedelta(hours=8),
        status="IN_PROGRESS",
        priority="NORMAL",
        source="interface",
        revision=2,
        created_by=principal.profile.id,
        created_at=entered_second - timedelta(hours=4),
    )
    definition = {
        "stages": [
            {"id": str(first_id), "name": "Briefing", "code": "BRIEFING", "color": "#64748B", "position": 1, "defaultAssigneeId": None, "expectedDurationHours": 4},
            {"id": str(second_id), "name": "Produção", "code": "PRODUCAO", "color": "#2563EB", "position": 2, "defaultAssigneeId": None, "expectedDurationHours": 8},
            {"id": str(third_id), "name": "Aprovação", "code": "APROVACAO", "color": "#7C3AED", "position": 3, "defaultAssigneeId": None, "expectedDurationHours": 2},
        ]
    }
    version = WorkflowVersion(
        id=version_id,
        organization_id=principal.membership.organization_id,
        workflow_id=workflow_id,
        version=3,
        definition=definition,
    )
    workflow = Workflow(
        id=workflow_id,
        organization_id=principal.membership.organization_id,
        name="Campanha",
        code="CAMPANHA",
        is_default=False,
        active=True,
    )
    update = DemandUpdate(
        id=uuid.uuid4(),
        demand_id=demand.id,
        created_by=principal.profile.id,
        kind="STAGE_CHANGED",
        summary="Etapa alterada para Produção.",
        payload={"fromStageId": str(first_id), "toStageId": str(second_id)},
        created_at=entered_second,
    )
    db = MagicMock(spec=Session)
    db.scalar.return_value = demand
    db.scalars.return_value = iter([update])

    def get_model(model: object, identifier: object) -> object | None:
        if model is WorkflowVersion and identifier == version_id:
            return version
        if model is Workflow and identifier == workflow_id:
            return workflow
        return None

    db.get.side_effect = get_model

    result = get_demand_timeline(demand.id, principal, db)

    assert result.version == 3
    assert [stage.state for stage in result.stages] == ["completed", "current", "upcoming"]
    assert result.stages[0].left_at == entered_second
    assert result.stages[2].forecast_at == demand.forecast_at + timedelta(hours=2)


def test_stage_plan_records_advance_skip_and_return_states() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    third_id = uuid.uuid4()
    version_id = uuid.uuid4()
    demand_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    instances = [
        DemandStageInstance(
            id=uuid.uuid4(),
            organization_id=organization_id,
            demand_id=demand_id,
            workflow_version_id=version_id,
            workflow_stage_id=stage_id,
            position=position,
            state="current" if position == 1 else "upcoming",
            revision=1,
        )
        for position, stage_id in enumerate((first_id, second_id, third_id), start=1)
    ]
    moved_at = datetime(2026, 9, 30, 14, tzinfo=UTC)

    move_stage_plan(instances, first_id, second_id, action="advance", moved_at=moved_at)
    assert [item.state for item in instances] == ["completed", "current", "upcoming"]

    move_stage_plan(instances, second_id, third_id, action="skip", moved_at=moved_at)
    assert [item.state for item in instances] == ["completed", "skipped", "current"]

    move_stage_plan(instances, third_id, second_id, action="return", moved_at=moved_at)
    assert [item.state for item in instances] == ["completed", "current", "upcoming"]


def test_stage_deadlines_are_weighted_and_finish_at_demand_deadline() -> None:
    organization_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    version_id = uuid.uuid4()
    demand_id = uuid.uuid4()
    stage_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    start = datetime(2026, 10, 1, 9, tzinfo=UTC)
    deadline = start + timedelta(days=10)
    version = WorkflowVersion(
        id=version_id,
        organization_id=organization_id,
        workflow_id=workflow_id,
        version=1,
        definition={
            "stages": [
                {"id": str(stage_ids[0]), "position": 1, "expectedDurationHours": 3},
                {"id": str(stage_ids[1]), "position": 2, "expectedDurationHours": 1},
                {"id": str(stage_ids[2]), "position": 3, "expectedDurationHours": 1},
            ]
        },
    )
    instances = [
        DemandStageInstance(
            id=uuid.uuid4(),
            organization_id=organization_id,
            demand_id=demand_id,
            workflow_version_id=version_id,
            workflow_stage_id=stage_id,
            position=index,
            state="current" if index == 1 else "upcoming",
            revision=1,
        )
        for index, stage_id in enumerate(stage_ids, start=1)
    ]

    rebalance_stage_deadlines(instances, version, deadline, now=start)

    assert instances[0].deadline_at == start + timedelta(days=6)
    assert instances[1].deadline_at == start + timedelta(days=8)
    assert instances[2].deadline_at == deadline
    assert [item.forecast_at for item in instances] == [item.deadline_at for item in instances]

def test_stage_risk_prioritizes_overdue_and_forecast_overrun() -> None:
    now = datetime(2026, 9, 30, 14, tzinfo=UTC)
    instance = DemandStageInstance(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        demand_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        workflow_stage_id=uuid.uuid4(),
        position=1,
        state="current",
        deadline_at=now - timedelta(hours=1),
        forecast_at=now + timedelta(hours=2),
    )
    assert stage_risk(instance, now) == "overdue"

    instance.deadline_at = now + timedelta(hours=1)
    assert stage_risk(instance, now) == "at_risk"

    instance.state = "completed"
    assert stage_risk(instance, now) == "none"


def test_handoff_requires_open_timer_to_be_closed() -> None:
    principal = _principal()
    demand = Demand(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        public_id="DMD-2026-000012",
        title="Vídeo com timer aberto",
        current_stage_id=uuid.uuid4(),
        status="IN_PROGRESS",
        priority="NORMAL",
        source="interface",
        revision=1,
        created_by=principal.profile.id,
    )
    db = MagicMock(spec=Session)
    db.scalar.return_value = uuid.uuid4()

    with pytest.raises(ApiError) as caught:
        validate_stage_handoff(db, demand, require_checklist=False)

    assert caught.value.code == "active_timer_requires_closure"


def test_handoff_requires_mandatory_checklist_to_be_completed() -> None:
    principal = _principal()
    required_id = uuid.uuid4()
    demand = Demand(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        public_id="DMD-2026-000013",
        title="Campanha com checklist pendente",
        current_stage_id=uuid.uuid4(),
        status="IN_PROGRESS",
        priority="NORMAL",
        source="interface",
        revision=1,
        created_by=principal.profile.id,
    )
    db = MagicMock(spec=Session)
    db.scalar.return_value = None
    db.scalars.side_effect = [iter([required_id]), iter([])]

    with pytest.raises(ApiError) as caught:
        validate_stage_handoff(db, demand, require_checklist=True)

    assert caught.value.code == "required_checklist_incomplete"


def test_stage_rejects_inactive_default_assignee() -> None:
    principal = _principal()
    stage = WorkflowStage(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        name="Produção",
        code="PRODUCAO",
        color="#7C3AED",
        position=4,
        revision=2,
        active=True,
    )
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [stage, None]
    payload = WorkflowStageUpdate(
        name=stage.name,
        code=stage.code,
        color=stage.color,
        position=stage.position,
        defaultAssigneeId=uuid.uuid4(),
        expectedDurationHours=24,
        expectedRevision=stage.revision,
        active=True,
    )

    with pytest.raises(ApiError) as caught:
        update_workflow_stage(stage.id, payload, principal, db)

    assert caught.value.code == "default_assignee_invalid"
    db.commit.assert_not_called()
def test_workflow_input_normalizes_reusable_model_code() -> None:
    payload = WorkflowInput(
        name="  Produção de vídeo  ",
        code="Vídeo social",
        description="Etapas padrão para vídeos.",
        isDefault=False,
    )

    assert payload.name == "Produção de vídeo"
    assert payload.code == "V_DEO_SOCIAL"
