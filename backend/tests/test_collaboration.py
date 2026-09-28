import uuid
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.collaboration import (
    CommentCreate,
    CommentUpdate,
    can_change_comment,
    create_comment,
    update_comment,
)
from app.auth.service import Principal
from app.models import (
    AuditEvent,
    Comment,
    CommentEdit,
    Demand,
    Membership,
    MembershipStatus,
    PermissionRole,
    UserProfile,
    utc_now,
)


def _principal(*, code: str = "collaborator", profile_id: uuid.UUID | None = None) -> Principal:
    organization_id = uuid.uuid4()
    profile = UserProfile(
        id=profile_id or uuid.uuid4(),
        auth_user_id=uuid.uuid4(),
        email=f"{code}@example.com",
        full_name=code.title(),
    )
    membership = Membership(
        id=uuid.uuid4(),
        organization_id=organization_id,
        user_profile_id=profile.id,
        status=MembershipStatus.ACTIVE,
    )
    permissions = (
        ["demands:read", "demands:write"]
        if code == "coordinator"
        else ["demands:read", "demands:work"]
    )
    role = PermissionRole(
        id=uuid.uuid4(),
        organization_id=organization_id,
        code=code,
        name=code.title(),
        permissions=permissions,
    )
    return Principal(MagicMock(), profile, membership, role)


def _demand(principal: Principal) -> Demand:
    return Demand(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        public_id="DMD-2026-000101",
        title="Campanha institucional",
        status="WAITING_EXECUTION",
        priority="NORMAL",
        source="interface",
        revision=1,
        created_by=principal.profile.id,
    )


def test_comment_content_is_trimmed_and_rejects_blank_text() -> None:
    assert CommentCreate(content="  Decisão registrada.\n").content == "Decisão registrada."
    with pytest.raises(ValidationError):
        CommentCreate(content=" \n\t ")


def test_comment_permissions_allow_author_or_coordinator() -> None:
    author_id = uuid.uuid4()
    author = _principal(profile_id=author_id)
    colleague = _principal()
    coordinator = _principal(code="coordinator")
    comment = Comment(
        id=uuid.uuid4(),
        demand_id=uuid.uuid4(),
        author_id=author_id,
        content="Texto",
        revision=1,
    )

    assert can_change_comment(author, comment)
    assert not can_change_comment(colleague, comment)
    assert can_change_comment(coordinator, comment)

    comment.deleted_at = utc_now()
    assert not can_change_comment(author, comment)
    assert not can_change_comment(coordinator, comment)


def test_create_comment_registers_audit_and_returns_editable_activity() -> None:
    principal = _principal()
    demand = _demand(principal)
    db = MagicMock(spec=Session)
    db.scalar.return_value = demand

    def assign_database_values() -> None:
        comment = db.add.call_args_list[0].args[0]
        assert isinstance(comment, Comment)
        comment.id = uuid.uuid4()
        comment.created_at = utc_now()
        comment.updated_at = comment.created_at

    db.flush.side_effect = assign_database_values

    result = create_comment(
        demand.id,
        CommentCreate(content="Material aprovado para revisão."),
        principal,
        db,
    )

    added = [call.args[0] for call in db.add.call_args_list]
    assert isinstance(added[0], Comment)
    assert any(isinstance(value, AuditEvent) and value.event_type == "COMMENT_CREATED" for value in added)
    assert result.item_type == "comment"
    assert result.content == "Material aprovado para revisão."
    assert result.can_edit
    assert result.can_delete
    db.commit.assert_called_once()


def test_update_comment_preserves_previous_content_and_increments_revision() -> None:
    principal = _principal()
    demand = _demand(principal)
    comment = Comment(
        id=uuid.uuid4(),
        demand_id=demand.id,
        author_id=principal.profile.id,
        content="Versão inicial",
        revision=1,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [demand, comment]
    db.get.return_value = principal.profile

    result = update_comment(
        demand.id,
        comment.id,
        CommentUpdate(content="Versão revisada", expectedRevision=1),
        principal,
        db,
    )

    added = [call.args[0] for call in db.add.call_args_list]
    edit = next(value for value in added if isinstance(value, CommentEdit))
    assert edit.previous_content == "Versão inicial"
    assert edit.new_content == "Versão revisada"
    assert result.content == "Versão revisada"
    assert result.revision == 2
    assert result.edited_at is not None
    db.commit.assert_called_once()
