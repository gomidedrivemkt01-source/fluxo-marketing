import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.access import require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import AuditEvent, Membership, MembershipStatus, PermissionRole, UserProfile

router = APIRouter(prefix="/users", tags=["Usuários"])


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    state: str
    role: str | None
    revision: int


class ApproveUserRequest(BaseModel):
    role: str = Field(pattern=r"^(admin|coordinator|collaborator|viewer)$")
    expected_revision: int = Field(alias="expectedRevision", ge=1)


@router.get("", response_model=list[UserOut])
def list_users(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> list[UserOut]:
    require_permission(principal, "users:read")
    rows = db.execute(
        select(Membership, UserProfile, PermissionRole)
        .join(UserProfile, UserProfile.id == Membership.user_profile_id)
        .outerjoin(PermissionRole, PermissionRole.id == Membership.permission_role_id)
        .where(Membership.organization_id == principal.membership.organization_id)
        .order_by(UserProfile.full_name)
    ).all()
    return [
        UserOut(
            id=membership.id,
            name=profile.full_name,
            email=profile.email,
            state=membership.status.value,
            role=role.code if role else None,
            revision=membership.revision,
        )
        for membership, profile, role in rows
    ]


@router.post(
    "/{membership_id}/approve",
    response_model=UserOut,
    dependencies=[Depends(require_csrf)],
)
def approve_user(
    membership_id: uuid.UUID,
    payload: ApproveUserRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> UserOut:
    require_permission(principal, "users:manage")
    membership = db.scalar(
        select(Membership)
        .where(
            Membership.id == membership_id,
            Membership.organization_id == principal.membership.organization_id,
        )
        .with_for_update()
    )
    if not membership:
        raise ApiError(404, "user_not_found", "Usuário não encontrado.")
    if membership.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O cadastro foi alterado. Atualize a tela.")
    role = db.scalar(
        select(PermissionRole).where(
            PermissionRole.organization_id == membership.organization_id,
            PermissionRole.code == payload.role,
        )
    )
    if not role:
        raise ApiError(422, "role_not_found", "Perfil de permissão inválido.")
    before = {"state": membership.status.value, "roleId": str(membership.permission_role_id)}
    membership.permission_role_id = role.id
    membership.status = MembershipStatus.ACTIVE
    membership.approved_by = principal.profile.id
    membership.approved_at = datetime.now(UTC)
    membership.suspended_at = None
    membership.revision += 1
    db.add(
        AuditEvent(
            organization_id=membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type="MEMBERSHIP_APPROVED",
            metadata_json={
                "membershipId": str(membership.id),
                "before": before,
                "after": {"state": membership.status.value, "role": role.code},
            },
        )
    )
    db.commit()
    profile = db.get(UserProfile, membership.user_profile_id)
    assert profile is not None
    return UserOut(
        id=membership.id,
        name=profile.full_name,
        email=profile.email,
        state=membership.status.value,
        role=role.code,
        revision=membership.revision,
    )
