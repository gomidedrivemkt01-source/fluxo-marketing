import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.api.catalogs import (
    WorkflowStageReorder,
    WorkflowStageUpdate,
    reorder_workflow_stages,
    update_workflow_stage,
)
from app.api.errors import ApiError
from app.auth.service import Principal
from app.models import (
    AuditEvent,
    Membership,
    MembershipStatus,
    PermissionRole,
    UserProfile,
    WorkflowStage,
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
        permissions=["catalog:write"],
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
