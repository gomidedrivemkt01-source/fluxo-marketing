import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.access import require_any_permission, require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import (
    AuditEvent,
    Comment,
    CommentEdit,
    Demand,
    DemandUpdate,
    DemandWatcher,
    UserProfile,
    utc_now,
)

router = APIRouter(prefix="/demands", tags=["Colaboração"])


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("O comentário não pode ficar vazio.")
        return normalized


class CommentUpdate(CommentCreate):
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class CommentDelete(BaseModel):
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class ActivityItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    item_type: str = Field(alias="itemType")
    kind: str
    summary: str
    content: str | None
    actor_id: uuid.UUID = Field(alias="actorId")
    actor_name: str = Field(alias="actorName")
    actor_avatar_url: str | None = Field(alias="actorAvatarUrl")
    revision: int | None
    edited_at: datetime | None = Field(alias="editedAt")
    deleted_at: datetime | None = Field(alias="deletedAt")
    can_edit: bool = Field(alias="canEdit")
    can_delete: bool = Field(alias="canDelete")
    created_at: datetime = Field(alias="createdAt")


class ActivityPageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[ActivityItemOut]
    next_cursor: datetime | None = Field(alias="nextCursor")


class WatcherOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    name: str
    avatar_url: str | None = Field(alias="avatarUrl")
    added_at: datetime = Field(alias="addedAt")
    is_current_user: bool = Field(alias="isCurrentUser")


def _avatar_url(profile: UserProfile) -> str | None:
    if not profile.avatar_path:
        return None
    return f"/api/v1/users/{profile.id}/avatar?v={profile.revision}"


def _get_demand(db: Session, demand_id: uuid.UUID, principal: Principal) -> Demand:
    demand = db.scalar(
        select(Demand).where(
            Demand.id == demand_id,
            Demand.organization_id == principal.membership.organization_id,
            Demand.deleted_at.is_(None),
        )
    )
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    return demand


def can_change_comment(principal: Principal, comment: Comment) -> bool:
    if comment.deleted_at:
        return False
    if comment.author_id == principal.profile.id:
        return True
    permissions = set(principal.role.permissions if principal.role else [])
    return "*" in permissions or "demands:write" in permissions


def _activity_from_comment(
    comment: Comment, author: UserProfile, principal: Principal
) -> ActivityItemOut:
    deleted = comment.deleted_at is not None
    allowed = can_change_comment(principal, comment)
    return ActivityItemOut(
        id=comment.id,
        item_type="comment",
        kind="COMMENT_DELETED" if deleted else "COMMENT",
        summary="Comentário removido." if deleted else f"{author.full_name} comentou.",
        content=None if deleted else comment.content,
        actor_id=author.id,
        actor_name=author.full_name,
        actor_avatar_url=_avatar_url(author),
        revision=comment.revision,
        edited_at=comment.edited_at,
        deleted_at=comment.deleted_at,
        can_edit=allowed,
        can_delete=allowed,
        created_at=comment.created_at,
    )


def _activity_from_update(update: DemandUpdate, author: UserProfile) -> ActivityItemOut:
    return ActivityItemOut(
        id=update.id,
        item_type="event",
        kind=update.kind,
        summary=update.summary,
        content=None,
        actor_id=author.id,
        actor_name=author.full_name,
        actor_avatar_url=_avatar_url(author),
        revision=None,
        edited_at=None,
        deleted_at=None,
        can_edit=False,
        can_delete=False,
        created_at=update.created_at,
    )


def _audit(principal: Principal, event_type: str, metadata: dict[str, object]) -> AuditEvent:
    return AuditEvent(
        organization_id=principal.membership.organization_id,
        actor_user_id=principal.profile.id,
        event_type=event_type,
        metadata_json=metadata,
    )


@router.get("/{demand_id}/activity", response_model=ActivityPageOut)
def list_activity(
    demand_id: uuid.UUID,
    before: datetime | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ActivityPageOut:
    require_permission(principal, "demands:read")
    demand = _get_demand(db, demand_id, principal)

    comments_query = select(Comment).where(Comment.demand_id == demand.id)
    updates_query = select(DemandUpdate).where(DemandUpdate.demand_id == demand.id)
    if before:
        comments_query = comments_query.where(Comment.created_at < before)
        updates_query = updates_query.where(DemandUpdate.created_at < before)
    comments = list(
        db.scalars(comments_query.order_by(Comment.created_at.desc()).limit(limit + 1))
    )
    updates = list(
        db.scalars(updates_query.order_by(DemandUpdate.created_at.desc()).limit(limit + 1))
    )

    profile_ids = {comment.author_id for comment in comments} | {
        update.created_by for update in updates
    }
    profiles = {
        profile.id: profile
        for profile in db.scalars(select(UserProfile).where(UserProfile.id.in_(profile_ids)))
    }
    candidates: list[ActivityItemOut] = []
    for comment in comments:
        author = profiles.get(comment.author_id)
        if author:
            candidates.append(_activity_from_comment(comment, author, principal))
    for update in updates:
        author = profiles.get(update.created_by)
        if author:
            candidates.append(_activity_from_update(update, author))
    candidates.sort(key=lambda item: item.created_at, reverse=True)
    has_more = len(candidates) > limit
    items = candidates[:limit]
    return ActivityPageOut(
        items=items,
        next_cursor=items[-1].created_at if has_more and items else None,
    )


@router.post(
    "/{demand_id}/comments",
    response_model=ActivityItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_comment(
    demand_id: uuid.UUID,
    payload: CommentCreate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ActivityItemOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    comment = Comment(
        demand_id=demand.id,
        author_id=principal.profile.id,
        content=payload.content,
    )
    db.add(comment)
    db.flush()
    db.add(
        _audit(
            principal,
            "COMMENT_CREATED",
            {"demandId": str(demand.id), "commentId": str(comment.id)},
        )
    )
    db.commit()
    db.refresh(comment)
    return _activity_from_comment(comment, principal.profile, principal)


@router.put(
    "/{demand_id}/comments/{comment_id}",
    response_model=ActivityItemOut,
    dependencies=[Depends(require_csrf)],
)
def update_comment(
    demand_id: uuid.UUID,
    comment_id: uuid.UUID,
    payload: CommentUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ActivityItemOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    comment = db.scalar(
        select(Comment)
        .where(Comment.id == comment_id, Comment.demand_id == demand.id)
        .with_for_update()
    )
    if not comment:
        raise ApiError(404, "comment_not_found", "Comentário não encontrado.")
    if not can_change_comment(principal, comment):
        raise ApiError(403, "comment_edit_denied", "Você não pode editar este comentário.")
    if comment.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O comentário foi alterado. Atualize a atividade.")
    if comment.content == payload.content:
        author = db.get(UserProfile, comment.author_id) or principal.profile
        return _activity_from_comment(comment, author, principal)

    previous_content = comment.content
    changed_at = utc_now()
    comment.content = payload.content
    comment.revision += 1
    comment.edited_at = changed_at
    comment.updated_at = changed_at
    db.add(
        CommentEdit(
            comment_id=comment.id,
            edited_by=principal.profile.id,
            previous_content=previous_content,
            new_content=comment.content,
        )
    )
    db.add(
        _audit(
            principal,
            "COMMENT_EDITED",
            {
                "demandId": str(demand.id),
                "commentId": str(comment.id),
                "revision": comment.revision,
            },
        )
    )
    db.commit()
    db.refresh(comment)
    author = db.get(UserProfile, comment.author_id) or principal.profile
    return _activity_from_comment(comment, author, principal)


@router.delete(
    "/{demand_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_comment(
    demand_id: uuid.UUID,
    comment_id: uuid.UUID,
    payload: CommentDelete,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Response:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    comment = db.scalar(
        select(Comment)
        .where(Comment.id == comment_id, Comment.demand_id == demand.id)
        .with_for_update()
    )
    if not comment:
        raise ApiError(404, "comment_not_found", "Comentário não encontrado.")
    if not can_change_comment(principal, comment):
        raise ApiError(403, "comment_delete_denied", "Você não pode remover este comentário.")
    if comment.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O comentário foi alterado. Atualize a atividade.")
    changed_at = utc_now()
    comment.deleted_at = changed_at
    comment.updated_at = changed_at
    comment.revision += 1
    db.add(
        _audit(
            principal,
            "COMMENT_DELETED",
            {"demandId": str(demand.id), "commentId": str(comment.id)},
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{demand_id}/watchers", response_model=list[WatcherOut])
def list_watchers(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[WatcherOut]:
    require_permission(principal, "demands:read")
    demand = _get_demand(db, demand_id, principal)
    rows = db.execute(
        select(DemandWatcher, UserProfile)
        .join(UserProfile, UserProfile.id == DemandWatcher.user_profile_id)
        .where(DemandWatcher.demand_id == demand.id)
        .order_by(UserProfile.full_name)
    ).all()
    return [
        WatcherOut(
            id=profile.id,
            name=profile.full_name,
            avatar_url=_avatar_url(profile),
            added_at=watcher.created_at,
            is_current_user=profile.id == principal.profile.id,
        )
        for watcher, profile in rows
    ]


@router.put(
    "/{demand_id}/watchers/me",
    response_model=WatcherOut,
    dependencies=[Depends(require_csrf)],
)
def follow_demand(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> WatcherOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    watcher = db.get(DemandWatcher, (demand.id, principal.profile.id))
    if not watcher:
        watcher = DemandWatcher(
            demand_id=demand.id,
            user_profile_id=principal.profile.id,
            added_by=principal.profile.id,
        )
        db.add(watcher)
        db.flush()
        db.add(
            DemandUpdate(
                demand_id=demand.id,
                created_by=principal.profile.id,
                kind="WATCHER_ADDED",
                summary=f"{principal.profile.full_name} começou a acompanhar a demanda.",
                payload={"profileId": str(principal.profile.id)},
            )
        )
        db.add(
            _audit(
                principal,
                "DEMAND_WATCHER_ADDED",
                {"demandId": str(demand.id), "profileId": str(principal.profile.id)},
            )
        )
        db.commit()
        db.refresh(watcher)
    return WatcherOut(
        id=principal.profile.id,
        name=principal.profile.full_name,
        avatar_url=_avatar_url(principal.profile),
        added_at=watcher.created_at,
        is_current_user=True,
    )


@router.delete(
    "/{demand_id}/watchers/me",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def unfollow_demand(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Response:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    watcher = db.get(DemandWatcher, (demand.id, principal.profile.id))
    if watcher:
        db.delete(watcher)
        db.add(
            DemandUpdate(
                demand_id=demand.id,
                created_by=principal.profile.id,
                kind="WATCHER_REMOVED",
                summary=f"{principal.profile.full_name} deixou de acompanhar a demanda.",
                payload={"profileId": str(principal.profile.id)},
            )
        )
        db.add(
            _audit(
                principal,
                "DEMAND_WATCHER_REMOVED",
                {"demandId": str(demand.id), "profileId": str(principal.profile.id)},
            )
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
