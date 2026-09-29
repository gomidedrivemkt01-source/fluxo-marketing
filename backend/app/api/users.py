import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Response, UploadFile
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.access import require_active, require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import (
    AuditEvent,
    Membership,
    MembershipStatus,
    PermissionRole,
    UserProfile,
    WorkflowStage,
    utc_now,
)

router = APIRouter(prefix="/users", tags=["Usuários"])


class UserOut(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID = Field(alias="profileId")
    name: str
    email: EmailStr
    state: str
    role: str | None
    revision: int
    avatar_url: str | None = Field(alias="avatarUrl")


class ApproveUserRequest(BaseModel):
    role: str = Field(pattern=r"^(admin|coordinator|collaborator|viewer)$")
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class ProfileOut(BaseModel):
    profile_id: uuid.UUID = Field(alias="profileId")
    name: str
    email: EmailStr
    timezone: str
    role: str | None
    revision: int
    avatar_url: str | None = Field(alias="avatarUrl")
    preferences: dict[str, object]


class SavedViewUpdate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")
    name: str = Field(min_length=2, max_length=40)
    query: str = Field(default="", max_length=120)
    company_id: str = Field(default="ALL", alias="companyId", max_length=40)
    status: Literal[
        "ALL",
        "WAITING_EXECUTION",
        "IN_PROGRESS",
        "WAITING_INFORMATION",
        "WAITING_APPROVAL",
        "BLOCKED",
        "SCHEDULED",
        "COMPLETED",
    ] = "ALL"
    priority: Literal["ALL", "LOW", "NORMAL", "HIGH", "URGENT"] = "ALL"
    focus_view: Literal[
        "all", "inbox", "today", "upcoming", "overdue", "waiting", "delegated"
    ] = Field(default="all", alias="focusView")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())


class PreferencesUpdate(BaseModel):
    demand_view: Literal["kanban", "list"] = Field(alias="demandView")
    show_empty_stages: bool = Field(alias="showEmptyStages")
    stage_order: list[uuid.UUID] = Field(default_factory=list, alias="stageOrder", max_length=50)
    focus_view: Literal[
        "all", "inbox", "today", "upcoming", "overdue", "waiting", "delegated"
    ] = Field(default="all", alias="focusView")
    saved_views: list[SavedViewUpdate] = Field(
        default_factory=list, alias="savedViews", max_length=12
    )


class UserOptionOut(BaseModel):
    id: uuid.UUID
    name: str
    avatar_url: str | None = Field(alias="avatarUrl")


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(default="America/Sao_Paulo", max_length=80)
    expected_revision: int = Field(alias="expectedRevision", ge=1)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())


def profile_out(principal: Principal) -> ProfileOut:
    preferences: dict[str, object] = {
        "demandView": "kanban",
        "showEmptyStages": True,
        "stageOrder": [],
        "focusView": "all",
        "savedViews": [],
    }
    preferences.update(principal.profile.workspace_preferences or {})
    return ProfileOut(
        profileId=principal.profile.id,
        name=principal.profile.full_name,
        email=principal.profile.email,
        timezone=principal.profile.timezone,
        role=principal.role.code if principal.role else None,
        revision=principal.profile.revision,
        avatarUrl=(
            f"/api/v1/users/me/avatar?v={principal.profile.revision}"
            if principal.profile.avatar_path
            else None
        ),
        preferences=preferences,
    )


@router.get("/me", response_model=ProfileOut)
def get_my_profile(principal: Principal = Depends(get_principal)) -> ProfileOut:
    require_active(principal)
    return profile_out(principal)


@router.put(
    "/me",
    response_model=ProfileOut,
    dependencies=[Depends(require_csrf)],
)
def update_my_profile(
    payload: ProfileUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ProfileOut:
    require_active(principal)
    profile = db.get(UserProfile, principal.profile.id)
    assert profile is not None
    if profile.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "Seu perfil foi alterado. Atualize a tela.")
    before = {"name": profile.full_name, "timezone": profile.timezone}
    profile.full_name = payload.name
    profile.timezone = payload.timezone
    profile.revision += 1
    profile.updated_at = utc_now()
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=profile.id,
            event_type="PROFILE_UPDATED",
            metadata_json={
                "before": before,
                "after": {"name": profile.full_name, "timezone": profile.timezone},
            },
        )
    )
    db.commit()
    db.refresh(profile)
    refreshed = Principal(principal.session, profile, principal.membership, principal.role)
    return profile_out(refreshed)


@router.put(
    "/me/preferences",
    response_model=ProfileOut,
    dependencies=[Depends(require_csrf)],
)
def update_my_preferences(
    payload: PreferencesUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ProfileOut:
    require_active(principal)
    if payload.stage_order:
        valid_ids = set(
            db.scalars(
                select(WorkflowStage.id).where(
                    WorkflowStage.organization_id == principal.membership.organization_id,
                    WorkflowStage.id.in_(payload.stage_order),
                )
            )
        )
        if valid_ids != set(payload.stage_order):
            raise ApiError(422, "stage_order_invalid", "A ordem de etapas é inválida.")
    profile = db.get(UserProfile, principal.profile.id)
    assert profile is not None
    profile.workspace_preferences = {
        "demandView": payload.demand_view,
        "showEmptyStages": payload.show_empty_stages,
        "stageOrder": [str(value) for value in payload.stage_order],
        "focusView": payload.focus_view,
        "savedViews": [
            {
                "id": view.id,
                "name": view.name,
                "query": view.query,
                "companyId": view.company_id,
                "status": view.status,
                "priority": view.priority,
                "focusView": view.focus_view,
            }
            for view in payload.saved_views
        ],
    }
    profile.updated_at = utc_now()
    db.commit()
    db.refresh(profile)
    refreshed = Principal(principal.session, profile, principal.membership, principal.role)
    return profile_out(refreshed)


@router.get("/options", response_model=list[UserOptionOut])
def list_user_options(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> list[UserOptionOut]:
    require_active(principal)
    rows = db.execute(
        select(UserProfile)
        .join(Membership, Membership.user_profile_id == UserProfile.id)
        .where(
            Membership.organization_id == principal.membership.organization_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .order_by(UserProfile.full_name)
    ).scalars()
    return [
        UserOptionOut(
            id=profile.id,
            name=profile.full_name,
            avatarUrl=(
                f"/api/v1/users/{profile.id}/avatar?v={profile.revision}"
                if profile.avatar_path
                else None
            ),
        )
        for profile in rows
    ]


@router.get("/me/avatar", response_class=Response)
def get_my_avatar(principal: Principal = Depends(get_principal)) -> Response:
    require_active(principal)
    if not principal.profile.avatar_data or not principal.profile.avatar_content_type:
        raise ApiError(404, "avatar_not_found", "Foto de perfil não encontrada.")
    return Response(
        content=principal.profile.avatar_data,
        media_type=principal.profile.avatar_content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{profile_id}/avatar", response_class=Response)
def get_profile_avatar(
    profile_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Response:
    require_active(principal)
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == principal.membership.organization_id,
            Membership.user_profile_id == profile_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    if not membership:
        raise ApiError(404, "avatar_not_found", "Foto de perfil não encontrada.")
    profile = db.get(UserProfile, profile_id)
    if not profile or not profile.avatar_data or not profile.avatar_content_type:
        raise ApiError(404, "avatar_not_found", "Foto de perfil não encontrada.")
    return Response(
        content=profile.avatar_data,
        media_type=profile.avatar_content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/me/avatar",
    response_model=ProfileOut,
    dependencies=[Depends(require_csrf)],
)
async def upload_my_avatar(
    avatar: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ProfileOut:
    require_active(principal)
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if avatar.content_type not in allowed:
        raise ApiError(422, "avatar_type_invalid", "Use uma imagem JPG, PNG ou WebP.")
    content = await avatar.read(2_000_001)
    if not content or len(content) > 2_000_000:
        raise ApiError(422, "avatar_size_invalid", "A foto deve ter no máximo 2 MB.")
    signatures = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }
    if not signatures.get(avatar.content_type, False):
        raise ApiError(422, "avatar_content_invalid", "O conteúdo da imagem não é válido.")
    profile = db.get(UserProfile, principal.profile.id)
    assert profile is not None
    profile.avatar_data = content
    profile.avatar_content_type = avatar.content_type
    profile.avatar_path = "database"
    profile.revision += 1
    profile.updated_at = utc_now()
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=profile.id,
            event_type="PROFILE_AVATAR_UPDATED",
            metadata_json={"contentType": avatar.content_type, "size": len(content)},
        )
    )
    db.commit()
    db.refresh(profile)
    refreshed = Principal(principal.session, profile, principal.membership, principal.role)
    return profile_out(refreshed)


@router.delete("/me/avatar", status_code=204, dependencies=[Depends(require_csrf)])
def delete_my_avatar(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> Response:
    require_active(principal)
    profile = db.get(UserProfile, principal.profile.id)
    assert profile is not None
    profile.avatar_data = None
    profile.avatar_content_type = None
    profile.avatar_path = None
    profile.revision += 1
    profile.updated_at = utc_now()
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=profile.id,
            event_type="PROFILE_AVATAR_REMOVED",
            metadata_json={},
        )
    )
    db.commit()
    return Response(status_code=204)


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
            profileId=profile.id,
            name=profile.full_name,
            email=profile.email,
            state=membership.status.value,
            role=role.code if role else None,
            revision=membership.revision,
            avatarUrl=(
                f"/api/v1/users/{profile.id}/avatar?v={profile.revision}"
                if profile.avatar_path
                else None
            ),
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
        profileId=profile.id,
        name=profile.full_name,
        email=profile.email,
        state=membership.status.value,
        role=role.code,
        revision=membership.revision,
        avatarUrl=(
            f"/api/v1/users/{profile.id}/avatar?v={profile.revision}"
            if profile.avatar_path
            else None
        ),
    )
