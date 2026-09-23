import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.supabase import AuthTokens
from app.core.config import Settings
from app.core.security import TokenCipher, hash_session_token, new_session_token
from app.models import (
    AppSession,
    AuditEvent,
    Membership,
    MembershipStatus,
    Organization,
    PermissionRole,
    PrivacyAcknowledgement,
    PrivacyNoticeVersion,
    UserProfile,
    utc_now,
)

SESSION_COOKIE = "fm_session"
CSRF_COOKIE = "fm_csrf"

ROLE_DEFINITIONS = {
    "admin": ["*"],
    "coordinator": [
        "users:read",
        "catalog:read",
        "catalog:write",
        "audit:read",
        "imports:write",
        "demands:read",
        "demands:write",
    ],
    "collaborator": ["catalog:read", "profile:write", "demands:read", "demands:work"],
    "viewer": ["catalog:read", "demands:read"],
}


@dataclass(frozen=True, slots=True)
class Principal:
    session: AppSession
    profile: UserProfile
    membership: Membership
    role: PermissionRole | None


@dataclass(frozen=True, slots=True)
class SessionIssue:
    token: str
    csrf_token: str
    principal: Principal


class SessionService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.cipher = TokenCipher(settings.token_encryption_key.get_secret_value())

    def _ensure_organization(self) -> Organization:
        organization = self.db.scalar(select(Organization).where(Organization.slug == "marketing"))
        if organization:
            return organization
        organization = Organization(
            name=self.settings.bootstrap_organization_name,
            slug="marketing",
        )
        self.db.add(organization)
        self.db.flush()
        for code, permissions in ROLE_DEFINITIONS.items():
            self.db.add(
                PermissionRole(
                    organization_id=organization.id,
                    code=code,
                    name={
                        "admin": "Administrador",
                        "coordinator": "Coordenador",
                        "collaborator": "Colaborador",
                        "viewer": "Visualizador",
                    }[code],
                    permissions=permissions,
                )
            )
        self.db.flush()
        return organization

    def ensure_identity(
        self,
        tokens: AuthTokens,
        *,
        fallback_name: str = "Usuário",
        privacy_notice_version: str | None = None,
        record_verification: bool = True,
    ) -> tuple[UserProfile, Membership]:
        auth_user_id = uuid.UUID(tokens.user.id)
        profile = self.db.scalar(
            select(UserProfile).where(UserProfile.auth_user_id == auth_user_id)
        )
        if not profile:
            profile = UserProfile(
                auth_user_id=auth_user_id,
                email=tokens.user.email,
                full_name=str(tokens.user.metadata.get("full_name") or fallback_name)[:160],
            )
            self.db.add(profile)
            self.db.flush()
        organization = self._ensure_organization()
        membership = self.db.scalar(
            select(Membership).where(
                Membership.organization_id == organization.id,
                Membership.user_profile_id == profile.id,
            )
        )
        if not membership:
            membership = Membership(
                organization_id=organization.id,
                user_profile_id=profile.id,
                status=MembershipStatus.PENDING_APPROVAL,
            )
            self.db.add(membership)
        self.db.flush()
        self._activate_bootstrap_admin(profile, membership)
        if privacy_notice_version:
            notice = self.db.scalar(
                select(PrivacyNoticeVersion).where(
                    PrivacyNoticeVersion.version == privacy_notice_version,
                    PrivacyNoticeVersion.active.is_(True),
                )
            )
            if notice:
                acknowledgement = self.db.scalar(
                    select(PrivacyAcknowledgement).where(
                        PrivacyAcknowledgement.user_profile_id == profile.id,
                        PrivacyAcknowledgement.notice_id == notice.id,
                    )
                )
                if not acknowledgement:
                    self.db.add(
                        PrivacyAcknowledgement(user_profile_id=profile.id, notice_id=notice.id)
                    )
        if record_verification:
            self.db.add(
                AuditEvent(
                    organization_id=organization.id,
                    actor_user_id=profile.id,
                    event_type="EMAIL_VERIFIED",
                    metadata_json={"authUserId": str(auth_user_id)},
                )
            )
        self.db.commit()
        self.db.refresh(profile)
        self.db.refresh(membership)
        return profile, membership

    def _activate_bootstrap_admin(self, profile: UserProfile, membership: Membership) -> None:
        configured_email = self.settings.bootstrap_admin_email
        if not configured_email or profile.email.lower() != str(configured_email).lower():
            return
        current_role = (
            self.db.get(PermissionRole, membership.permission_role_id)
            if membership.permission_role_id
            else None
        )
        if (
            membership.status == MembershipStatus.ACTIVE
            and current_role is not None
            and current_role.code == "admin"
        ):
            return
        active_admins = self.db.scalar(
            select(func.count())
            .select_from(Membership)
            .join(PermissionRole, PermissionRole.id == Membership.permission_role_id)
            .where(
                Membership.organization_id == membership.organization_id,
                PermissionRole.code == "admin",
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        if active_admins:
            return
        admin_role = self.db.scalar(
            select(PermissionRole).where(
                PermissionRole.organization_id == membership.organization_id,
                PermissionRole.code == "admin",
            )
        )
        if not admin_role:
            raise RuntimeError("Papel de administrador não encontrado.")
        membership.permission_role_id = admin_role.id
        membership.status = MembershipStatus.ACTIVE
        membership.approved_by = profile.id
        membership.approved_at = utc_now()
        membership.revision += 1
        self.db.add(
            AuditEvent(
                organization_id=membership.organization_id,
                actor_user_id=profile.id,
                event_type="INITIAL_ADMIN_BOOTSTRAPPED",
                metadata_json={"membershipId": str(membership.id)},
            )
        )

    def issue(
        self, tokens: AuthTokens, profile: UserProfile, membership: Membership
    ) -> SessionIssue:
        now = utc_now()
        raw_token = new_session_token()
        csrf_token = secrets.token_urlsafe(32)
        app_session = AppSession(
            user_profile_id=profile.id,
            token_hash=hash_session_token(
                raw_token, self.settings.session_secret.get_secret_value()
            ),
            access_token_ciphertext=self.cipher.encrypt(tokens.access_token),
            refresh_token_ciphertext=self.cipher.encrypt(tokens.refresh_token),
            expires_at=now + timedelta(days=7),
            idle_expires_at=now + timedelta(hours=24),
            last_seen_at=now,
        )
        self.db.add(app_session)
        self.db.add(
            AuditEvent(
                organization_id=membership.organization_id,
                actor_user_id=profile.id,
                event_type="SESSION_CREATED",
                metadata_json={"sessionId": str(app_session.id)},
            )
        )
        self.db.commit()
        role = self.db.get(PermissionRole, membership.permission_role_id)
        return SessionIssue(
            raw_token, csrf_token, Principal(app_session, profile, membership, role)
        )

    def principal(self, raw_token: str | None) -> Principal:
        if not raw_token:
            raise ApiError(401, "not_authenticated", "Faça login para continuar.")
        token_hash = hash_session_token(raw_token, self.settings.session_secret.get_secret_value())
        session = self.db.scalar(select(AppSession).where(AppSession.token_hash == token_hash))
        now = datetime.now(UTC)
        if (
            not session
            or session.revoked_at is not None
            or session.expires_at <= now
            or session.idle_expires_at <= now
        ):
            raise ApiError(401, "session_expired", "Sua sessão expirou. Faça login novamente.")
        profile = self.db.get(UserProfile, session.user_profile_id)
        membership = self.db.scalar(
            select(Membership).where(Membership.user_profile_id == session.user_profile_id)
        )
        if not profile or not membership:
            raise ApiError(401, "account_unavailable", "A conta não está disponível.")
        session.last_seen_at = now
        session.idle_expires_at = now + timedelta(hours=24)
        role = self.db.get(PermissionRole, membership.permission_role_id)
        self.db.commit()
        return Principal(session, profile, membership, role)

    def revoke(self, principal: Principal, *, all_sessions: bool = False) -> None:
        values = {"revoked_at": utc_now()}
        if all_sessions:
            self.db.execute(
                update(AppSession)
                .where(
                    AppSession.user_profile_id == principal.profile.id,
                    AppSession.revoked_at.is_(None),
                )
                .values(**values)
            )
        else:
            principal.session.revoked_at = values["revoked_at"]
        self.db.add(
            AuditEvent(
                organization_id=principal.membership.organization_id,
                actor_user_id=principal.profile.id,
                event_type="ALL_SESSIONS_REVOKED" if all_sessions else "SESSION_REVOKED",
                metadata_json={},
            )
        )
        self.db.commit()

    def revoke_profile_sessions(self, profile_id: uuid.UUID) -> None:
        self.db.execute(
            update(AppSession)
            .where(AppSession.user_profile_id == profile_id, AppSession.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
        self.db.commit()

    def profile_by_auth_user_id(self, auth_user_id: str) -> UserProfile | None:
        return self.db.scalar(
            select(UserProfile).where(UserProfile.auth_user_id == uuid.UUID(auth_user_id))
        )

    def recovery_token(self, access_token: str) -> str:
        return self.cipher.encrypt(access_token)

    def consume_recovery_token(self, token: str) -> str:
        try:
            return self.cipher.decrypt(token, ttl=600)
        except ValueError as exc:
            raise ApiError(400, "recovery_expired", "O código de recuperação expirou.") from exc


def commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", "O registro já existe ou foi alterado.") from exc
