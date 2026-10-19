"""Indicadores operacionais consolidados da organização."""

import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.access import require_permission
from app.api.errors import ApiError
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
    MembershipStatus,
    TimeEntry,
    UserProfile,
    WorkflowStage,
    utc_now,
)

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


class ReportTrendPointOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: date
    created: int
    completed: int
    tracked_minutes: int = Field(alias="trackedMinutes")


class ReportCapacityOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    profile_id: uuid.UUID = Field(alias="profileId")
    profile_name: str = Field(alias="profileName")
    active_demands: int = Field(alias="activeDemands")
    expected_minutes: int = Field(alias="expectedMinutes")
    tracked_minutes: int = Field(alias="trackedMinutes")


class ReportStagePerformanceOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stage_id: uuid.UUID = Field(alias="stageId")
    stage_name: str = Field(alias="stageName")
    color: str
    visits: int
    average_hours: float = Field(alias="averageHours")
    total_hours: float = Field(alias="totalHours")
    sla_hours: int | None = Field(alias="slaHours")
    within_sla: int = Field(alias="withinSla")
    breached_sla: int = Field(alias="breachedSla")
    sla_rate: int | None = Field(alias="slaRate")
    returns: int


class OperationalReportOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    period_days: int = Field(alias="periodDays")
    period_started_at: datetime = Field(alias="periodStartedAt")
    period_ended_at: datetime = Field(alias="periodEndedAt")
    generated_at: datetime = Field(alias="generatedAt")
    scope: str
    scope_profile_id: uuid.UUID | None = Field(alias="scopeProfileId")
    scope_profile_name: str | None = Field(alias="scopeProfileName")
    can_view_team: bool = Field(alias="canViewTeam")
    summary: ReportSummaryOut
    by_status: list[ReportBreakdownOut] = Field(alias="byStatus")
    by_company: list[ReportBreakdownOut] = Field(alias="byCompany")
    by_category: list[ReportBreakdownOut] = Field(alias="byCategory")
    by_assignee: list[ReportBreakdownOut] = Field(alias="byAssignee")
    by_stage: list[ReportBreakdownOut] = Field(alias="byStage")
    trend_granularity: str = Field(alias="trendGranularity")
    trend: list[ReportTrendPointOut]
    capacity: list[ReportCapacityOut]
    stage_performance: list[ReportStagePerformanceOut] = Field(alias="stagePerformance")
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
        key=lambda item: (-item.count, -item.total_minutes, -item.overdue, item.label.casefold()),
    )


def build_operational_report(
    *,
    demands: list[Demand],
    entries: list[TimeEntry],
    completion_events: list[DemandUpdate] | None = None,
    stage_visits: list[DemandStageVisit] | None = None,
    companies: dict[uuid.UUID, Company],
    categories: dict[uuid.UUID, DemandCategory],
    profiles: dict[uuid.UUID, UserProfile],
    stages: dict[uuid.UUID, WorkflowStage],
    days: int,
    now: datetime,
    period_started_at: datetime | None = None,
    period_ended_at: datetime | None = None,
    scope: str = "team",
    scope_profile_id: uuid.UUID | None = None,
    scope_profile_name: str | None = None,
    can_view_team: bool = True,
    timezone_name: str = "America/Sao_Paulo",
) -> OperationalReportOut:
    period_started_at = period_started_at or now - timedelta(days=days)
    period_ended_at = period_ended_at or now
    completion_events = completion_events or []
    stage_visits = stage_visits or []
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

    try:
        report_timezone: ZoneInfo | timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        report_timezone = timezone(timedelta(hours=-3), name="America/Sao_Paulo")

    if days <= 45:
        trend_granularity = "day"
    elif days <= 180:
        trend_granularity = "week"
    else:
        trend_granularity = "month"

    def trend_bucket(value: datetime) -> date:
        local_date = value.astimezone(report_timezone).date()
        if trend_granularity == "week":
            return local_date - timedelta(days=local_date.weekday())
        if trend_granularity == "month":
            return local_date.replace(day=1)
        return local_date

    trend_values: dict[date, dict[str, int]] = defaultdict(
        lambda: {"created": 0, "completed": 0, "tracked_minutes": 0}
    )
    local_start = period_started_at.astimezone(report_timezone).date()
    local_end = period_ended_at.astimezone(report_timezone).date()
    cursor = trend_bucket(period_started_at)
    while cursor <= local_end:
        trend_values[cursor]
        if trend_granularity == "month":
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            cursor += timedelta(days=7 if trend_granularity == "week" else 1)
    for demand in demands:
        if period_started_at <= demand.created_at <= period_ended_at:
            trend_values[trend_bucket(demand.created_at)]["created"] += 1
    for event in completion_events:
        if period_started_at <= event.created_at <= period_ended_at:
            trend_values[trend_bucket(event.created_at)]["completed"] += 1
    for entry in entries:
        trend_values[trend_bucket(entry.started_at)]["tracked_minutes"] += (
            entry.duration_minutes or 0
        )
    trend = [
        ReportTrendPointOut(
            date=bucket_date,
            created=values["created"],
            completed=values["completed"],
            tracked_minutes=values["tracked_minutes"],
        )
        for bucket_date, values in sorted(trend_values.items())
        if bucket_date <= local_end and (
            trend_granularity != "day" or bucket_date >= local_start
        )
    ]

    capacity_values: dict[uuid.UUID, dict[str, int]] = defaultdict(
        lambda: {"active_demands": 0, "expected_minutes": 0, "tracked_minutes": 0}
    )
    for demand in active:
        if demand.current_assignee_id:
            capacity_values[demand.current_assignee_id]["active_demands"] += 1
            capacity_values[demand.current_assignee_id]["expected_minutes"] += (
                demand.expected_effort_minutes or 0
            )
    for entry in entries:
        capacity_values[entry.user_profile_id]["tracked_minutes"] += entry.duration_minutes or 0
    capacity = sorted(
        [
            ReportCapacityOut(
                profile_id=profile_id,
                profile_name=(profiles[profile_id].full_name if profile_id in profiles else "Usuário"),
                active_demands=values["active_demands"],
                expected_minutes=values["expected_minutes"],
                tracked_minutes=values["tracked_minutes"],
            )
            for profile_id, values in capacity_values.items()
        ],
        key=lambda item: (-item.tracked_minutes, -item.expected_minutes, item.profile_name.casefold()),
    )

    performance_values: dict[uuid.UUID, dict[str, float | int]] = defaultdict(
        lambda: {
            "visits": 0,
            "total_seconds": 0.0,
            "within_sla": 0,
            "breached_sla": 0,
            "returns": 0,
        }
    )
    for visit in stage_visits:
        stage = stages.get(visit.workflow_stage_id)
        if not stage:
            continue
        visit_end = visit.left_at or min(now, period_ended_at)
        observed_start = max(visit.entered_at, period_started_at)
        observed_end = min(visit_end, period_ended_at)
        if observed_end < observed_start:
            continue
        elapsed_seconds = max(0.0, (observed_end - observed_start).total_seconds())
        values = performance_values[visit.workflow_stage_id]
        values["visits"] += 1
        values["total_seconds"] += elapsed_seconds
        values["returns"] += int(visit.action == "RETURN")
        if stage.sla_hours:
            full_elapsed = max(0.0, (visit_end - visit.entered_at).total_seconds())
            if full_elapsed <= stage.sla_hours * 3600:
                values["within_sla"] += 1
            else:
                values["breached_sla"] += 1
    stage_performance: list[ReportStagePerformanceOut] = []
    for stage_id, values in performance_values.items():
        stage = stages[stage_id]
        visits_count = int(values["visits"])
        within_sla = int(values["within_sla"])
        breached_sla = int(values["breached_sla"])
        measured_sla = within_sla + breached_sla
        total_hours = float(values["total_seconds"]) / 3600
        stage_performance.append(
            ReportStagePerformanceOut(
                stage_id=stage_id,
                stage_name=stage.name,
                color=stage.color,
                visits=visits_count,
                average_hours=round(total_hours / visits_count, 1) if visits_count else 0,
                total_hours=round(total_hours, 1),
                sla_hours=stage.sla_hours,
                within_sla=within_sla,
                breached_sla=breached_sla,
                sla_rate=round((within_sla / measured_sla) * 100) if measured_sla else None,
                returns=int(values["returns"]),
            )
        )
    stage_performance.sort(key=lambda item: (-item.total_hours, item.stage_name.casefold()))

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
        scope=scope,
        scope_profile_id=scope_profile_id,
        scope_profile_name=scope_profile_name,
        can_view_team=can_view_team,
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
        trend_granularity=trend_granularity,
        trend=trend,
        capacity=capacity,
        stage_performance=stage_performance,
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
        user_timezone: ZoneInfo | timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        user_timezone = timezone(timedelta(hours=-3), name="America/Sao_Paulo")
    started_at = datetime.combine(start_date, time.min, tzinfo=user_timezone).astimezone(UTC)
    ended_at = datetime.combine(end_date, time.max, tzinfo=user_timezone).astimezone(UTC)
    return period_days, started_at, ended_at


def resolve_report_scope(
    *,
    role_code: str | None,
    own_profile_id: uuid.UUID,
    requested_profile_id: uuid.UUID | None,
) -> tuple[bool, uuid.UUID | None]:
    """Resolve o escopo sem confiar no filtro enviado pelo navegador."""
    can_view_team = role_code in {"admin", "coordinator"}
    if can_view_team:
        return True, requested_profile_id
    if requested_profile_id and requested_profile_id != own_profile_id:
        raise ApiError(
            403,
            "report_scope_forbidden",
            "Você pode consultar apenas o próprio relatório.",
        )
    return False, own_profile_id


@router.get("/operational", response_model=OperationalReportOut)
def operational_report(
    days: int = Query(default=30, ge=7, le=365),
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    assignee_id: uuid.UUID | None = Query(default=None, alias="assigneeId"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> OperationalReportOut:
    require_permission(principal, "demands:read")
    organization_id = principal.membership.organization_id
    can_view_team, scope_profile_id = resolve_report_scope(
        role_code=principal.role.code if principal.role else None,
        own_profile_id=principal.profile.id,
        requested_profile_id=assignee_id,
    )
    scope_profile: UserProfile | None = None
    if scope_profile_id == principal.profile.id:
        scope_profile = principal.profile
    elif scope_profile_id:
        scope_profile = db.scalar(
            select(UserProfile)
            .join(Membership, Membership.user_profile_id == UserProfile.id)
            .where(
                UserProfile.id == scope_profile_id,
                Membership.organization_id == organization_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        if not scope_profile:
            raise ApiError(
                404,
                "report_profile_not_found",
                "A pessoa selecionada não pertence à equipe ativa.",
            )
    now = utc_now()
    period_days, period_started_at, period_ended_at = resolve_report_period(
        days=days,
        start_date=start_date,
        end_date=end_date,
        timezone_name=principal.profile.timezone,
        now=now,
    )
    demand_statement = select(Demand).where(
        Demand.organization_id == organization_id,
        or_(
            Demand.status == "COMPLETED",
            and_(Demand.deleted_at.is_(None), Demand.archived_at.is_(None)),
        ),
    )
    if scope_profile_id:
        demand_statement = demand_statement.where(Demand.current_assignee_id == scope_profile_id)
    demands = list(db.scalars(demand_statement))

    time_statement = (
        select(TimeEntry)
        .join(Demand, Demand.id == TimeEntry.demand_id)
        .where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.deleted_at.is_(None),
            TimeEntry.started_at >= period_started_at,
            TimeEntry.started_at <= period_ended_at,
            TimeEntry.duration_minutes.is_not(None),
            Demand.organization_id == organization_id,
        )
    )
    if scope_profile_id:
        time_statement = time_statement.where(TimeEntry.user_profile_id == scope_profile_id)
    entries = list(db.scalars(time_statement))
    completion_statement = (
        select(DemandUpdate)
        .join(Demand, Demand.id == DemandUpdate.demand_id)
        .where(
            Demand.organization_id == organization_id,
            DemandUpdate.kind == "DEMAND_COMPLETED",
            DemandUpdate.created_at >= period_started_at,
            DemandUpdate.created_at <= period_ended_at,
        )
    )
    if scope_profile_id:
        completion_statement = completion_statement.where(
            DemandUpdate.created_by == scope_profile_id
        )
    completion_events = list(db.scalars(completion_statement))
    visit_statement = select(DemandStageVisit).where(
        DemandStageVisit.organization_id == organization_id,
        DemandStageVisit.entered_at <= period_ended_at,
        or_(
            DemandStageVisit.left_at.is_(None),
            DemandStageVisit.left_at >= period_started_at,
        ),
    )
    if scope_profile_id:
        visit_statement = visit_statement.where(DemandStageVisit.assignee_id == scope_profile_id)
    stage_visits = list(db.scalars(visit_statement))
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
    assignee_ids.update(entry.user_profile_id for entry in entries)
    assignee_ids.update(visit.assignee_id for visit in stage_visits if visit.assignee_id)
    profiles = (
        {
            item.id: item
            for item in db.scalars(select(UserProfile).where(UserProfile.id.in_(assignee_ids)))
        }
        if assignee_ids
        else {}
    )
    if scope_profile:
        profiles[scope_profile.id] = scope_profile
    return build_operational_report(
        demands=demands,
        entries=entries,
        completion_events=completion_events,
        stage_visits=stage_visits,
        companies=companies,
        categories=categories,
        profiles=profiles,
        stages=stages,
        days=period_days,
        now=now,
        period_started_at=period_started_at,
        period_ended_at=period_ended_at,
        scope="person" if scope_profile_id else "team",
        scope_profile_id=scope_profile_id,
        scope_profile_name=scope_profile.full_name if scope_profile else None,
        can_view_team=can_view_team,
        timezone_name=principal.profile.timezone,
    )
