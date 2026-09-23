import uuid
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.auth.service import SessionService
from app.core.config import Settings
from app.models import AuditEvent, Membership, MembershipStatus, PermissionRole, UserProfile


def _settings(email: str | None) -> Settings:
    return Settings(
        bootstrap_admin_email=email,
        session_secret="session-secret-with-more-than-thirty-two-characters",
        token_encryption_key="encryption-secret-with-more-than-thirty-two-characters",
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="test-key",
    )


def test_configured_email_becomes_first_admin() -> None:
    db = MagicMock(spec=Session)
    organization_id = uuid.uuid4()
    profile = UserProfile(
        id=uuid.uuid4(),
        auth_user_id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Admin",
    )
    membership = Membership(
        id=uuid.uuid4(),
        organization_id=organization_id,
        user_profile_id=profile.id,
        status=MembershipStatus.PENDING_APPROVAL,
        revision=1,
    )
    admin_role = PermissionRole(
        id=uuid.uuid4(),
        organization_id=organization_id,
        code="admin",
        name="Administrador",
        permissions=["*"],
    )
    db.get.return_value = None
    db.scalar.side_effect = [0, admin_role]

    SessionService(db, _settings("admin@example.com"))._activate_bootstrap_admin(
        profile, membership
    )

    assert membership.permission_role_id == admin_role.id
    assert membership.status == MembershipStatus.ACTIVE
    assert membership.approved_by == profile.id
    assert membership.approved_at is not None
    assert membership.revision == 2
    audit = db.add.call_args.args[0]
    assert isinstance(audit, AuditEvent)
    assert audit.event_type == "INITIAL_ADMIN_BOOTSTRAPPED"


def test_other_email_remains_pending() -> None:
    db = MagicMock(spec=Session)
    profile = UserProfile(
        id=uuid.uuid4(),
        auth_user_id=uuid.uuid4(),
        email="pessoa@example.com",
        full_name="Pessoa",
    )
    membership = Membership(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        user_profile_id=profile.id,
        status=MembershipStatus.PENDING_APPROVAL,
        revision=1,
    )

    SessionService(db, _settings("admin@example.com"))._activate_bootstrap_admin(
        profile, membership
    )

    assert membership.status == MembershipStatus.PENDING_APPROVAL
    assert membership.permission_role_id is None
    db.get.assert_not_called()
    db.scalar.assert_not_called()
