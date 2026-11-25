"""Per-user operational reminders and administrator-controlled thresholds."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.access import require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import (
    AuditEvent,
    Demand,
    DemandStageVisit,
    NotificationPolicy,
    Organization,
    WorkflowStage,
    utc_now,
)

router = APIRouter(prefix="/notifications", tags=["Alertas operacionais"])


class PolicyOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)
    enabled: bool = True
    warning_days: int = Field(default=7, alias="warningDays", ge=1, le=90)
    due_soon: bool = Field(default=True, alias="dueSoon")
    overdue: bool = True
    approvals: bool = True
    include_participating: bool = Field(default=True, alias="includeParticipating")
    revision: int = 0


class PolicyUpdate(PolicyOut):
    expected_revision: int = Field(alias="expectedRevision", ge=0)


def policy_for(db: Session, organization_id: uuid.UUID) -> PolicyOut:
    policy = db.get(NotificationPolicy, organization_id)
    return PolicyOut.model_validate(policy) if policy else PolicyOut()


def alert_reasons(
    demand: Demand, policy: PolicyOut, now: datetime, stage_name: str = ""
) -> list[str]:
    if (
        not policy.enabled
        or demand.status == "COMPLETED"
        or demand.archived_at
        or demand.deleted_at
    ):
        return []
    reasons = []
    if demand.deadline_at:
        remaining = demand.deadline_at - now
        if policy.overdue and remaining.total_seconds() < 0:
            reasons.append("Prazo vencido")
        elif policy.due_soon and timedelta(0) <= remaining < timedelta(days=policy.warning_days):
            reasons.append(f"Prazo em menos de {policy.warning_days} dias")
    if policy.approvals and (
        demand.status == "WAITING_APPROVAL" or "aprova" in stage_name.casefold()
    ):
        reasons.append("Aprovação pendente")
    return reasons


@router.get("/policy", response_model=PolicyOut)
def get_policy(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> PolicyOut:
    require_permission(principal, "demands:read")
    return policy_for(db, principal.membership.organization_id)


@router.put("/policy", response_model=PolicyOut, dependencies=[Depends(require_csrf)])
def save_policy(
    payload: PolicyUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> PolicyOut:
    if not principal.role or principal.role.code != "admin":
        raise ApiError(
            403, "admin_required", "Somente administradores podem configurar os alertas."
        )
    # Serialize the initial creation as well as later edits.
    db.scalar(
        select(Organization)
        .where(Organization.id == principal.membership.organization_id)
        .with_for_update()
    )
    policy = db.get(NotificationPolicy, principal.membership.organization_id)
    if (policy.revision if policy else 0) != payload.expected_revision:
        raise ApiError(
            409, "revision_conflict", "A configuração foi alterada. Atualize e tente novamente."
        )
    before = (PolicyOut.model_validate(policy) if policy else PolicyOut()).model_dump(by_alias=True)
    if policy is None:
        policy = NotificationPolicy(
            organization_id=principal.membership.organization_id, revision=0
        )
        db.add(policy)
    for field in (
        "enabled",
        "warning_days",
        "due_soon",
        "overdue",
        "approvals",
        "include_participating",
    ):
        setattr(policy, field, getattr(payload, field))
    policy.revision += 1
    policy.updated_by = principal.profile.id
    policy.updated_at = utc_now()
    db.add(
        AuditEvent(
            organization_id=policy.organization_id,
            actor_user_id=principal.profile.id,
            event_type="NOTIFICATION_POLICY_UPDATED",
            source="interface",
            metadata_json={
                "before": before,
                "after": payload.model_dump(by_alias=True, exclude={"expected_revision"}),
            },
        )
    )
    db.commit()
    return PolicyOut.model_validate(policy)


@router.get("/inbox")
def inbox(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> dict[str, Any]:
    require_permission(principal, "demands:read")
    policy = policy_for(db, principal.membership.organization_id)
    if not policy.enabled:
        return {"policy": policy.model_dump(by_alias=True), "items": [], "total": 0}
    participating = select(DemandStageVisit.demand_id).where(
        DemandStageVisit.organization_id == principal.membership.organization_id,
        DemandStageVisit.assignee_id == principal.profile.id,
        or_(
            DemandStageVisit.inferred.is_(False),
            DemandStageVisit.acceptance_snapshot["exitRecordedAt"].astext.is_not(None),
        ),
    )
    audience = Demand.current_assignee_id == principal.profile.id
    if policy.include_participating:
        audience = or_(audience, Demand.id.in_(participating))
    cards = db.execute(
        select(Demand, WorkflowStage.name)
        .outerjoin(WorkflowStage, WorkflowStage.id == Demand.current_stage_id)
        .where(
            Demand.organization_id == principal.membership.organization_id,
            Demand.deleted_at.is_(None),
            Demand.archived_at.is_(None),
            Demand.status != "COMPLETED",
            audience,
        )
    ).all()
    now = utc_now()
    items = []
    for card, stage_name in cards:
        reasons = alert_reasons(card, policy, now, stage_name or "")
        if reasons:
            items.append(
                {
                    "id": str(card.id),
                    "publicId": card.public_id,
                    "title": card.title,
                    "reason": " · ".join(reasons),
                    "deadlineAt": card.deadline_at,
                    "severity": "overdue" if "Prazo vencido" in reasons else "upcoming",
                    "participating": card.current_assignee_id != principal.profile.id,
                }
            )
    items.sort(
        key=lambda item: (
            item["severity"] != "overdue",
            item["deadlineAt"] or datetime.max.replace(tzinfo=now.tzinfo),
            item["title"],
        )
    )
    return {"policy": policy.model_dump(by_alias=True), "items": items, "total": len(items)}
