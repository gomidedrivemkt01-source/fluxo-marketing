import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.access import require_active
from app.api.errors import ApiError
from app.models import Demand, Membership, MembershipStatus, Workflow
from app.operational_management import (
    ResponsibilityChange,
    removal_preview,
    remove_person,
    resolve_assignment,
)


def test_principal_and_substitute_must_be_distinct():
    person = uuid.uuid4()
    with pytest.raises(ValidationError):
        ResponsibilityChange(
            roles=[
                {
                    "roleId": uuid.uuid4(),
                    "primaryProfileId": person,
                    "fallbackProfileId": person,
                    "expectedRevision": 1,
                }
            ]
        )


def test_duplicate_roles_are_rejected():
    change = {
        "roleId": uuid.uuid4(),
        "primaryProfileId": None,
        "fallbackProfileId": None,
        "expectedRevision": 1,
    }
    with pytest.raises(ValidationError):
        ResponsibilityChange(roles=[change, change])


def test_suspended_direct_owner_uses_active_substitute():
    inactive, substitute = uuid.uuid4(), uuid.uuid4()
    assert (
        resolve_assignment(
            {"defaultAssigneeId": str(inactive), "fallbackUserId": str(substitute)},
            {},
            {substitute},
            MagicMock(spec=Demand),
        )
        == substitute
    )


def test_removed_membership_cannot_use_an_existing_session():
    principal = MagicMock()
    principal.membership = Membership(status=MembershipStatus.ACTIVE, removed_at=datetime.now(UTC))
    with pytest.raises(ApiError) as error:
        require_active(principal)
    assert error.value.code == "account_removed"


def test_default_workflow_cannot_be_removed():
    principal = MagicMock()
    db = MagicMock(spec=Session)
    db.scalar.return_value = Workflow(is_default=True)
    with pytest.raises(ApiError) as error:
        removal_preview(db, principal, uuid.uuid4())
    assert error.value.code == "default_workflow_required"
    db.commit.assert_not_called()


def test_person_must_be_suspended_before_removal():
    principal = MagicMock()
    principal.membership.id = uuid.uuid4()
    db = MagicMock(spec=Session)
    member = Membership(id=uuid.uuid4(), revision=1, status=MembershipStatus.ACTIVE)
    db.scalar.return_value = member
    with pytest.raises(ApiError) as error:
        remove_person(db, principal, member.id, 1)
    assert error.value.code == "suspend_first"
    db.delete.assert_not_called()


def test_person_cannot_remove_their_own_account():
    principal = MagicMock()
    principal.membership.id = uuid.uuid4()
    db = MagicMock(spec=Session)
    db.scalar.return_value = Membership(
        id=principal.membership.id, status=MembershipStatus.SUSPENDED
    )
    with pytest.raises(ApiError) as error:
        remove_person(db, principal, principal.membership.id, 1)
    assert error.value.code == "self_removal"
    db.commit.assert_not_called()
