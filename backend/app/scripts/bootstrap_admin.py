import argparse
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import AuditEvent, Membership, MembershipStatus, PermissionRole, UserProfile


def main() -> None:
    parser = argparse.ArgumentParser(description="Promove o primeiro administrador verificado")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    email = args.email.strip().lower()
    with SessionLocal.begin() as db:
        active_admins = db.scalar(
            select(func.count())
            .select_from(Membership)
            .join(PermissionRole, PermissionRole.id == Membership.permission_role_id)
            .where(PermissionRole.code == "admin", Membership.status == MembershipStatus.ACTIVE)
        )
        if active_admins:
            raise SystemExit("Bootstrap recusado: já existe administrador ativo.")
        row = db.execute(
            select(UserProfile, Membership)
            .join(Membership, Membership.user_profile_id == UserProfile.id)
            .where(func.lower(UserProfile.email) == email)
            .with_for_update()
        ).one_or_none()
        if not row:
            raise SystemExit("Cadastre e confirme esse e-mail na aplicação antes do bootstrap.")
        profile, membership = row
        role = db.scalar(
            select(PermissionRole).where(
                PermissionRole.organization_id == membership.organization_id,
                PermissionRole.code == "admin",
            )
        )
        if not role:
            raise SystemExit("Papel admin não encontrado; confira a migration inicial.")
        membership.permission_role_id = role.id
        membership.status = MembershipStatus.ACTIVE
        membership.approved_by = profile.id
        membership.approved_at = datetime.now(UTC)
        membership.revision += 1
        db.add(
            AuditEvent(
                organization_id=membership.organization_id,
                actor_user_id=profile.id,
                event_type="INITIAL_ADMIN_BOOTSTRAPPED",
                metadata_json={"membershipId": str(membership.id)},
            )
        )
    print(f"Administrador inicial ativado: {email}")


if __name__ == "__main__":
    main()
