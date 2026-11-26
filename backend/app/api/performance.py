"""Own daily/weekly performance; no assignee or team scope is accepted."""

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, load_only

from app.api.access import require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal
from app.auth.service import Principal
from app.database import get_db
from app.models import Demand, DemandStageVisit, DemandUpdate, TimeEntry, WorkflowVersion, utc_now
from app.personal_performance import TIMER_KINDS, build_personal_performance

router = APIRouter(prefix="/performance", tags=["Performance pessoal imediata"])


@router.get("/me")
def personal_performance(
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    gap_minutes: int = Query(default=90, alias="gapMinutes", ge=30, le=240),
    day_start: str = Query(
        default="08:00", alias="dayStart", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    ),
    day_end: str = Query(default="18:00", alias="dayEnd", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_permission(principal, "demands:read")
    try:
        zone = ZoneInfo(principal.profile.timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("America/Sao_Paulo")
    now = utc_now()
    today = now.astimezone(zone).date()
    if (start_date is None) != (end_date is None):
        raise ApiError(422, "performance_period_incomplete", "Informe as duas datas do período.")
    first, last = start_date or today, end_date or today
    if last < first or last > today or (last - first).days >= 31:
        raise ApiError(
            422, "performance_period_invalid", "Use um período de até 31 dias, encerrado até hoje."
        )
    if (
        not all(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) for value in [day_start, day_end])
        or day_start >= day_end
    ):
        raise ApiError(
            422,
            "performance_window_invalid",
            "O horário final de acompanhamento deve ser posterior ao inicial.",
        )
    start = datetime.combine(first, time.min, zone).astimezone(UTC)
    end = datetime.combine(last + timedelta(days=1), time.min, zone).astimezone(UTC)
    org = principal.membership.organization_id
    own = principal.profile.id
    owned_entries = list(
        db.scalars(
            select(TimeEntry)
            .options(
                load_only(
                    TimeEntry.id,
                    TimeEntry.demand_id,
                    TimeEntry.user_profile_id,
                    TimeEntry.source,
                    TimeEntry.state,
                    TimeEntry.started_at,
                    TimeEntry.ended_at,
                    TimeEntry.duration_minutes,
                    TimeEntry.deleted_at,
                    TimeEntry.created_at,
                )
            )
            .where(
                TimeEntry.organization_id == org,
                TimeEntry.user_profile_id == own,
                TimeEntry.deleted_at.is_(None),
            )
        )
    )
    participation = select(DemandStageVisit.demand_id).where(
        DemandStageVisit.organization_id == org,
        DemandStageVisit.assignee_id == own,
        or_(
            DemandStageVisit.inferred.is_(False),
            DemandStageVisit.acceptance_snapshot["exitRecordedAt"].astext.is_not(None),
        ),
    )
    cards = list(
        db.scalars(
            select(Demand).where(
                Demand.organization_id == org,
                or_(
                    Demand.current_assignee_id == own,
                    Demand.id.in_(participation),
                    Demand.id.in_({entry.demand_id for entry in owned_entries}),
                ),
            )
        )
    )
    card_ids = [card.id for card in cards]
    visits = (
        list(
            db.scalars(
                select(DemandStageVisit).where(
                    DemandStageVisit.organization_id == org,
                    DemandStageVisit.demand_id.in_(card_ids),
                )
            )
        )
        if cards
        else []
    )
    relevant_entry_ids = [
        str(entry.id)
        for entry in owned_entries
        if entry.demand_id in card_ids
        and min(entry.created_at, entry.started_at) <= min(end, now) + timedelta(minutes=1)
        and (entry.ended_at is None or entry.ended_at >= start)
    ]
    conditions = [DemandUpdate.kind == "DEMAND_COMPLETED"]
    if relevant_entry_ids:
        conditions.append(
            (DemandUpdate.kind.in_(TIMER_KINDS | {"TIME_ENTRY_UPDATED"}))
            & DemandUpdate.payload["timeEntryId"].astext.in_(relevant_entry_ids)
        )
    events = (
        list(
            db.scalars(
                select(DemandUpdate).where(DemandUpdate.demand_id.in_(card_ids), or_(*conditions))
            )
        )
        if cards
        else []
    )
    version_ids = {visit.workflow_version_id for visit in visits}
    versions = (
        {
            version.id: version
            for version in db.scalars(
                select(WorkflowVersion).where(
                    WorkflowVersion.organization_id == org, WorkflowVersion.id.in_(version_ids)
                )
            )
        }
        if version_ids
        else {}
    )
    result = build_personal_performance(
        profile_id=own,
        cards=cards,
        visits=visits,
        events=events,
        entries=owned_entries,
        versions=versions,
        start=start,
        end=end,
        now=now,
        zone=zone,
        gap_minutes=gap_minutes,
        day_start=time.fromisoformat(day_start),
        day_end=time.fromisoformat(day_end),
    )
    return {
        "profileId": str(own),
        "timezone": str(zone),
        "startDate": first,
        "endDate": last,
        "gapMinutes": gap_minutes,
        "dayStart": day_start,
        "dayEnd": day_end,
        **result,
    }
