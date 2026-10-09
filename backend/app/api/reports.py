"""Indicadores operacionais consolidados da organização."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.access import require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal
from app.auth.service import Principal
from app.database import get_db
from app.models import Company, Demand, DemandCategory, TimeEntry, UserProfile, WorkflowStage, utc_now

router = APIRouter(prefix="/reports", tags=["Relatórios"])


class ReportSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total_demands: int = Field(alias="totalDemands")
    created_in_period: int = Field(alias="createdInPeriod")
    completed_demands: int = Field(alias="completedDemands")
    overdue: int
    due_soon: int = Field(alias="dueSoon")
    blocked: int
    unassigned: int
    urgent: int
    tracked_minutes: int = Field(alias="trackedMinutes")
    expected_minutes: int = Field(alias="expectedMinutes")


class ReportBreakdownOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    label: str
    color: str | None = None
    count: int
    overdue: int
    total_minutes: int = Field(alias="totalMinutes")


class ReportAttentionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    public_id: str = Field(alias="publicId")
    title: str
    company_name: str | None = Field(alias="companyName")
    assignee_name: str | None = Field(alias="assigneeName")
    stage_name: str | None = Field(alias="stageName")
    status: str
    priority: str
    deadline_at: datetime | None = Field(alias="deadlineAt")
    reasons: list[str]


class OperationalReportOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    period_days: int = Field(alias="periodDays")
    period_started_at: datetime = Field(alias="periodStartedAt")
    period_ended_at: datetime = Field(alias="periodEndedAt")
    generated_at: datetime = Field(alias="generatedAt")
    summary: ReportSummaryOut
    by_status: list[ReportBreakdownOut] = Field(alias="byStatus")
    by_company: list[ReportBreakdownOut] = Field(alias="byCompany")
    by_category: list[ReportBreakdownOut] = Field(alias="byCategory")
    by_assignee: list[ReportBreakdownOut] = Field(alias="byAssignee")
    by_stage: list[ReportBreakdownOut] = Field(alias="byStage")
    attention: list[ReportAttentionOut]


STATUS_LABELS = {
    "WAITING_EXECUTION": "Aguardando execução",
    "IN_PROGRESS": "Em andamento",
    "WAITING_INFORMATION": "Aguardando informação",
    "WAITING_APPROVAL": "Aguardando aprovação",
    "BLOCKED": "Bloqueadas",
    "SCHEDULED": "Agendadas",
    "COMPLETED": "Concluídas",
}

STATUS_COLORS = {
    "WAITING_EXECUTION": "#D99A3D",
    "IN_PROGRESS": "#087F76",
    "WAITING_INFORMATION": "#64748B",
    "WAITING_APPROVAL": "#7C5CB8",
    "BLOCKED": "#C44E4E",
    "SCHEDULED": "#3578C8",
    "COMPLETED": "#2F8A57",
}


def _is_overdue(demand: Demand, now: datetime) -> bool:
    return bool(
        demand.deadline_at
        and demand.deadline_at < now
        and demand.status != "COMPLETED"
    )


def _breakdown(
    demands: list[Demand],
    *,
    identity: Callable[[Demand], str],
    labels: dict[str, str],
    colors: dict[str, str],
    time_by_demand: dict[uuid.UUID, int],
    now: datetime,
) -> list[ReportBreakdownOut]:
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"count": 0, "overdue": 0, "total_minutes": 0}
    )
    for demand in demands:
        key = identity(demand)
        buckets[key]["count"] += 1
        buckets[key]["overdue"] += int(_is_overdue(demand, now))
        buckets[key]["total_minutes"] += time_by_demand.get(demand.id, 0)
    return sorted(
        [
            ReportBreakdownOut(
                id=key,
                label=labels.get(key, "Não definido"),
                color=colors.get(key),
                count=values["count"],
                overdue=values["overdue"],
                total_minutes=values["total_minutes"],
            )
            for key, values in buckets.items()
        ],
        key=lambda item: (-item.count, -item.overdue, item.label.casefold()),
    )


def build_operational_report(
    *,
    demands: list[Demand],
    entries: list[TimeEntry],
    companies: dict[uuid.UUID, Company],
    categories: dict[uuid.UUID, DemandCategory],
    profiles: dict[uuid.UUID, UserProfile],
    stages: dict[uuid.UUID, WorkflowStage],
    days: int,
    now: datetime,
    period_started_at: datetime | None = None,
    period_ended_at: datetime | None = None,
) -> OperationalReportOut:
    period_started_at = period_started_at or now - timedelta(days=days)
    period_ended_at = period_ended_at or now
    active = [demand for demand in demands if demand.status != "COMPLETED"]
    time_by_demand: dict[uuid.UUID, int] = defaultdict(int)
    for entry in entries:
        time_by_demand[entry.demand_id] += entry.duration_minutes or 0

    company_labels = {str(item.id): item.name for item in companies.values()}
    company_colors = {str(item.id): item.color for item in companies.values()}
    category_labels = {str(item.id): item.name for item in categories.values()}
    category_colors = {str(item.id): item.color for item in categories.values()}
    profile_labels = {str(item.id): item.full_name for item in profiles.values()}
    stage_labels = {str(item.id): item.name for item in stages.values()}
    stage_colors = {str(item.id): item.color for item in stages.values()}
    missing = "__missing__"
    company_labels[missing] = "Sem empresa"
    category_labels[missing] = "Sem categoria"
    profile_labels[missing] = "Sem responsável"
    stage_labels[missing] = "Sem etapa"

    attention: list[ReportAttentionOut] = []
    for demand in active:
        reasons: list[str] = []
        if _is_overdue(demand, now):
            reasons.append("Prazo vencido")
        if demand.status == "BLOCKED":
            reasons.append("Bloqueada")
        if demand.priority == "URGENT":
            reasons.append("Urgente")
        if not demand.current_assignee_id:
            reasons.append("Sem responsável")
        if not reasons:
            continue
        attention.append(
            ReportAttentionOut(
                id=demand.id,
                public_id=demand.public_id,
                title=demand.title,
                company_name=(
                    companies[demand.primary_company_id].name
                    if demand.primary_company_id in companies
                    else None
                ),
                assignee_name=(
                    profiles[demand.current_assignee_id].full_name
                    if demand.current_assignee_id in profiles
                    else None
                ),
                stage_name=(
                    stages[demand.current_stage_id].name
                    if demand.current_stage_id in stages
                    else None
                ),
                status=demand.status,
                priority=demand.priority,
                deadline_at=demand.deadline_at,
                reasons=reasons,
            )
        )
    attention.sort(
        key=lambda item: (
            0 if "Prazo vencido" in item.reasons else 1,
            0 if "Bloqueada" in item.reasons else 1,
            item.deadline_at or datetime.max.replace(tzinfo=now.tzinfo),
            item.title.casefold(),
        )
    )

    return OperationalReportOut(
        period_days=days,
        period_started_at=period_started_at,
        period_ended_at=period_ended_at,
        generated_at=now,
        summary=ReportSummaryOut(
            total_demands=len(demands),
            created_in_period=sum(
                period_started_at <= demand.created_at <= period_ended_at for demand in demands
            ),
            completed_demands=sum(demand.status == "COMPLETED" for demand in demands),
            overdue=sum(_is_overdue(demand, now) for demand in demands),
            due_soon=sum(
                bool(demand.deadline_at and now <= demand.deadline_at <= now + timedelta(days=7))
                for demand in active
            ),
            blocked=sum(demand.status == "BLOCKED" for demand in active),
            unassigned=sum(not demand.current_assignee_id for demand in active),
            urgent=sum(demand.priority == "URGENT" for demand in active),
            tracked_minutes=sum(time_by_demand.values()),
            expected_minutes=sum(demand.expected_effort_minutes or 0 for demand in active),
        ),
        by_status=_breakdown(
            demands,
            identity=lambda demand: demand.status,
            labels=STATUS_LABELS,
            colors=STATUS_COLORS,
            time_by_demand=time_by_demand,
            now=now,
        ),
        by_company=_breakdown(
            demands,
            identity=lambda demand: str(demand.primary_company_id) if demand.primary_company_id else missing,
            labels=company_labels,
            colors=company_colors,
            time_by_demand=time_by_demand,
            now=now,
        ),
        by_category=_breakdown(
            demands,
            identity=lambda demand: str(demand.category_id) if demand.category_id else missing,
            labels=category_labels,
            colors=category_colors,
            time_by_demand=time_by_demand,
            now=now,
        ),
        by_assignee=_breakdown(
            active,
            identity=lambda demand: str(demand.current_assignee_id) if demand.current_assignee_id else missing,
            labels=profile_labels,
            colors={},
            time_by_demand=time_by_demand,
            now=now,
        ),
        by_stage=_breakdown(
            active,
            identity=lambda demand: str(demand.current_stage_id) if demand.current_stage_id else missing,
            labels=stage_labels,
            colors=stage_colors,
            time_by_demand=time_by_demand,
            now=now,
        ),
        attention=attention[:20],
    )


def resolve_report_period(
    *,
    days: int,
    start_date: date | None,
    end_date: date | None,
    timezone_name: str,
    now: datetime,
) -> tuple[int, datetime, datetime]:
    if bool(start_date) != bool(end_date):
        raise ApiError(
            422,
            "report_period_incomplete",
            "Informe as datas inicial e final do período personalizado.",
        )
    if not start_date or not end_date:
        return days, now - timedelta(days=days), now
    if end_date < start_date:
        raise ApiError(
            422,
            "report_period_invalid",
            "A data final deve ser igual ou posterior à data inicial.",
        )
    period_days = (end_date - start_date).days + 1
    if period_days > 1096:
        raise ApiError(
            422,
            "report_period_too_long",
            "O período personalizado pode abranger no máximo três anos.",
        )
    try:
        user_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        user_timezone = timezone(timedelta(hours=-3), name="America/Sao_Paulo")
    started_at = datetime.combine(start_date, time.min, tzinfo=user_timezone).astimezone(UTC)
    ended_at = datetime.combine(end_date, time.max, tzinfo=user_timezone).astimezone(UTC)
    return period_days, started_at, ended_at


@router.get("/operational", response_model=OperationalReportOut)
def operational_report(
    days: int = Query(default=30, ge=7, le=365),
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> OperationalReportOut:
    require_permission(principal, "demands:read")
    organization_id = principal.membership.organization_id
    now = utc_now()
    period_days, period_started_at, period_ended_at = resolve_report_period(
        days=days,
        start_date=start_date,
        end_date=end_date,
        timezone_name=principal.profile.timezone,
        now=now,
    )
    demands = list(
        db.scalars(
            select(Demand).where(
                Demand.organization_id == organization_id,
                Demand.deleted_at.is_(None),
                Demand.archived_at.is_(None),
            )
        )
    )
    demand_ids = {demand.id for demand in demands}
    entries = (
        list(
            db.scalars(
                select(TimeEntry).where(
                    TimeEntry.organization_id == organization_id,
                    TimeEntry.demand_id.in_(demand_ids),
                    TimeEntry.deleted_at.is_(None),
                    TimeEntry.started_at >= period_started_at,
                    TimeEntry.started_at <= period_ended_at,
                    TimeEntry.duration_minutes.is_not(None),
                )
            )
        )
        if demand_ids
        else []
    )
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
    stages = {
        item.id: item
        for item in db.scalars(
            select(WorkflowStage).where(WorkflowStage.organization_id == organization_id)
        )
    }
    assignee_ids = {demand.current_assignee_id for demand in demands if demand.current_assignee_id}
    profiles = (
        {
            item.id: item
            for item in db.scalars(select(UserProfile).where(UserProfile.id.in_(assignee_ids)))
        }
        if assignee_ids
        else {}
    )
    return build_operational_report(
        demands=demands,
        entries=entries,
        companies=companies,
        categories=categories,
        profiles=profiles,
        stages=stages,
        days=period_days,
        now=now,
        period_started_at=period_started_at,
        period_ended_at=period_ended_at,
    )
