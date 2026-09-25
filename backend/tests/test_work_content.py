import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.work_content import (
    BriefingFieldInput,
    ChecklistToggleInput,
    DemandBriefingInput,
    toggle_demand_checklist_item,
    update_demand_briefing,
)
from app.auth.service import Principal
from app.models import (
    AuditEvent,
    BriefingField,
    ChecklistTemplateItem,
    Demand,
    DemandChecklistItem,
    DemandUpdate,
    Membership,
    MembershipStatus,
    PermissionRole,
    UserProfile,
    WorkflowStage,
    utc_now,
)


def _principal() -> Principal:
    organization_id = uuid.uuid4()
    profile = UserProfile(
        id=uuid.uuid4(),
        auth_user_id=uuid.uuid4(),
        email="operacao@example.com",
        full_name="Operação",
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
        code="collaborator",
        name="Colaborador",
        permissions=["demands:read", "demands:work", "catalog:read"],
    )
    return Principal(MagicMock(), profile, membership, role)


def _demand(principal: Principal, *, category_id: uuid.UUID | None = None) -> Demand:
    return Demand(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        public_id="DMD-2026-000001",
        title="Campanha",
        category_id=category_id,
        status="WAITING_EXECUTION",
        priority="NORMAL",
        source="interface",
        revision=2,
        created_by=principal.profile.id,
        created_at=utc_now(),
    )


def test_briefing_field_normalizes_key_and_options() -> None:
    payload = BriefingFieldInput(
        label="  Objetivo principal  ",
        key="Objetivo da Campanha",
        fieldType="select",
        options=["Conversão", " Alcance ", "Conversão", ""],
        required=True,
        position=1,
    )

    assert payload.label == "Objetivo principal"
    assert payload.key == "objetivo_da_campanha"
    assert payload.options == ["Conversão", "Alcance"]


def test_required_briefing_field_blocks_incomplete_save() -> None:
    principal = _principal()
    category_id = uuid.uuid4()
    demand = _demand(principal, category_id=category_id)
    field = BriefingField(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        category_id=category_id,
        label="Objetivo",
        key="objetivo",
        field_type="text",
        options=[],
        required=True,
        position=1,
        active=True,
    )
    db = MagicMock(spec=Session)
    db.scalar.return_value = demand
    db.scalars.return_value = iter([field])

    with pytest.raises(ApiError) as caught:
        update_demand_briefing(
            demand.id,
            DemandBriefingInput(expectedRevision=2, answers=[]),
            principal,
            db,
        )

    assert caught.value.code == "briefing_required"
    db.commit.assert_not_called()


def test_checklist_toggle_updates_card_revision_and_history() -> None:
    principal = _principal()
    stage = WorkflowStage(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        name="Revisão",
        code="REVISAO",
        color="#D97706",
        position=5,
        active=True,
    )
    demand = _demand(principal)
    demand.current_stage_id = stage.id
    template = ChecklistTemplateItem(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        workflow_stage_id=stage.id,
        title="Revisar texto",
        position=1,
        required=True,
        active=True,
    )
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [demand, template, None]
    db.get.return_value = stage

    result = toggle_demand_checklist_item(
        demand.id,
        template.id,
        ChecklistToggleInput(completed=True, expectedRevision=2),
        principal,
        db,
    )

    assert result.revision == 3
    added = [call.args[0] for call in db.add.call_args_list]
    assert any(isinstance(value, DemandChecklistItem) and value.completed for value in added)
    assert any(isinstance(value, DemandUpdate) for value in added)
    assert any(isinstance(value, AuditEvent) for value in added)
    db.commit.assert_called_once()
