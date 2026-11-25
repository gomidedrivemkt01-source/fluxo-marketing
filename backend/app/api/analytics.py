"""Analytics with historical participant attribution and report privacy."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.analytics import build_analytics
from app.api.access import require_permission
from app.api.errors import ApiError
from app.api.notifications import policy_for
from app.api.reports import resolve_report_period, resolve_report_scope
from app.auth.dependencies import get_principal
from app.auth.service import Principal
from app.database import get_db
from app.models import (
    Company,
    Demand,
    DemandCategory,
    DemandStageVisit,
    DemandUpdate,
    Membership,
    TimeEntry,
    UserProfile,
    Workflow,
    WorkflowStage,
    WorkflowVersion,
    utc_now,
)

router = APIRouter(prefix="/reports", tags=["Análises de entregas"])


@router.get("/analytics")
def analytics_report(
    days: int = Query(default=30, ge=7, le=365),
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    assignee_id: uuid.UUID | None = Query(default=None, alias="assigneeId"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_permission(principal, "demands:read")
    can_view_team, scope_id = resolve_report_scope(
        role_code=principal.role.code if principal.role else None,
        own_profile_id=principal.profile.id,
        requested_profile_id=assignee_id,
    )
    organization_id = principal.membership.organization_id
    scope_profile = principal.profile if scope_id == principal.profile.id else None
    if scope_id and not scope_profile:
        scope_profile = db.scalar(
            select(UserProfile)
            .join(Membership, Membership.user_profile_id == UserProfile.id)
            .where(UserProfile.id == scope_id, Membership.organization_id == organization_id)
        )
        if not scope_profile:
            raise ApiError(
                404,
                "report_profile_not_found",
                "A pessoa selecionada não pertence a esta organização.",
            )
    now = utc_now()
    period_days, started, ended = resolve_report_period(
        days=days,
        start_date=start_date,
        end_date=end_date,
        timezone_name=principal.profile.timezone,
        now=now,
    )
    statement = select(Demand).where(Demand.organization_id == organization_id)
    if scope_id:
        participation = select(DemandStageVisit.demand_id).where(
            DemandStageVisit.organization_id == organization_id,
            DemandStageVisit.assignee_id == scope_id,
            or_(
                DemandStageVisit.inferred.is_(False),
                DemandStageVisit.acceptance_snapshot["exitRecordedAt"].astext.is_not(None),
            ),
        )
        recorded_time = select(TimeEntry.demand_id).where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.user_profile_id == scope_id,
            TimeEntry.deleted_at.is_(None),
        )
        statement = statement.where(
            or_(
                Demand.current_assignee_id == scope_id,
                Demand.id.in_(participation),
                Demand.id.in_(recorded_time),
            )
        )
    cards = list(db.scalars(statement))
    card_ids = [card.id for card in cards]
    visits = (
        list(
            db.scalars(
                select(DemandStageVisit).where(
                    DemandStageVisit.organization_id == organization_id,
                    DemandStageVisit.demand_id.in_(card_ids),
                )
            )
        )
        if card_ids
        else []
    )
    events = (
        list(
            db.scalars(
                select(DemandUpdate).where(
                    DemandUpdate.demand_id.in_(card_ids), DemandUpdate.kind == "DEMAND_COMPLETED"
                )
            )
        )
        if card_ids
        else []
    )
    entries_statement = select(TimeEntry).where(
        TimeEntry.organization_id == organization_id,
        TimeEntry.demand_id.in_(card_ids),
        TimeEntry.deleted_at.is_(None),
        TimeEntry.state == "COMPLETED",
        func.coalesce(TimeEntry.ended_at, TimeEntry.started_at) >= started,
        func.coalesce(TimeEntry.ended_at, TimeEntry.started_at) <= ended,
    )
    if scope_id:
        entries_statement = entries_statement.where(TimeEntry.user_profile_id == scope_id)
    entries = list(db.scalars(entries_statement)) if card_ids else []
    version_ids = {visit.workflow_version_id for visit in visits} | {
        card.workflow_version_id for card in cards if card.workflow_version_id
    }
    versions = (
        {
            item.id: item
            for item in db.scalars(
                select(WorkflowVersion).where(
                    WorkflowVersion.organization_id == organization_id,
                    WorkflowVersion.id.in_(version_ids),
                )
            )
        }
        if version_ids
        else {}
    )
    profile_ids = (
        {visit.assignee_id for visit in visits if visit.assignee_id}
        | {card.current_assignee_id for card in cards if card.current_assignee_id}
        | {entry.user_profile_id for entry in entries}
    )
    profiles = (
        {
            item.id: item
            for item in db.scalars(select(UserProfile).where(UserProfile.id.in_(profile_ids)))
        }
        if profile_ids
        else {}
    )
    stages = {
        item.id: item
        for item in db.scalars(
            select(WorkflowStage).where(WorkflowStage.organization_id == organization_id)
        )
    }
    workflows = {
        item.id: item
        for item in db.scalars(select(Workflow).where(Workflow.organization_id == organization_id))
    }
    companies = {
        item.id: item
        for item in db.scalars(select(Company).where(Company.organization_id == organization_id))
    }
    categories = {
        item.id: item
        for item in db.scalars(
            select(DemandCategory).where(DemandCategory.organization_id == organization_id)
        )
    }
    policy = policy_for(db, organization_id)
    result = build_analytics(
        demands=cards,
        visits=visits,
        events=events,
        entries=entries,
        versions=versions,
        profiles=profiles,
        stages=stages,
        workflows=workflows,
        companies=companies,
        categories=categories,
        scope_profile_id=scope_id,
        started_at=started,
        ended_at=ended,
        now=now,
        timezone_name=principal.profile.timezone,
        warning_days=policy.warning_days,
    )
    open_timer_statement = (
        select(func.count())
        .select_from(TimeEntry)
        .where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.deleted_at.is_(None),
            TimeEntry.state.in_(("RUNNING", "PAUSED")),
        )
    )
    if scope_id:
        open_timer_statement = open_timer_statement.where(TimeEntry.user_profile_id == scope_id)
    result["quality"]["openTimersExcluded"] = db.scalar(open_timer_statement) or 0
    return {
        "periodStartedAt": started,
        "periodEndedAt": ended,
        "periodDays": period_days,
        "generatedAt": now,
        "scope": "person" if scope_id else "team",
        "scopeProfileId": str(scope_id) if scope_id else None,
        "scopeProfileName": scope_profile.full_name if scope_profile else None,
        "canViewTeam": can_view_team,
        "warningDays": policy.warning_days,
        **result,
    }
