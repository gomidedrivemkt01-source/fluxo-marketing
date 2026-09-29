"""Apontamentos de tempo, timer e esforço previsto das demandas."""

import math
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.access import require_any_permission, require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import AuditEvent, Demand, DemandUpdate, TimeEntry, UserProfile, utc_now

router = APIRouter(prefix="/demands", tags=["Tempo e esforço"])


def _clean_note(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class ManualTimeEntryCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    started_at: datetime = Field(alias="startedAt")
    duration_minutes: int = Field(alias="durationMinutes", ge=1, le=1440)
    note: str | None = Field(default=None, max_length=1000)

    _normalize_note = field_validator("note")(_clean_note)


class TimeEntryEdit(ManualTimeEntryCreate):
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class TimeEntryDelete(BaseModel):
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class TimerStart(BaseModel):
    note: str | None = Field(default=None, max_length=1000)

    _normalize_note = field_validator("note")(_clean_note)


class TimerStop(BaseModel):
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class TimeEstimateUpdate(BaseModel):
    expected_effort_minutes: int | None = Field(
        default=None, alias="expectedEffortMinutes", ge=1, le=100_000
    )
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class TimeEntryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    user_id: uuid.UUID = Field(alias="userId")
    user_name: str = Field(alias="userName")
    source: str
    state: str
    started_at: datetime = Field(alias="startedAt")
    ended_at: datetime | None = Field(alias="endedAt")
    duration_minutes: int | None = Field(alias="durationMinutes")
    note: str | None
    revision: int
    can_edit: bool = Field(alias="canEdit")
    created_at: datetime = Field(alias="createdAt")


class TimeSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    expected_effort_minutes: int | None = Field(alias="expectedEffortMinutes")
    total_minutes: int = Field(alias="totalMinutes")
    my_total_minutes: int = Field(alias="myTotalMinutes")
    active_timer: TimeEntryOut | None = Field(alias="activeTimer")
    entries: list[TimeEntryOut]
    demand_revision: int = Field(alias="demandRevision")


class TimeEstimateOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    expected_effort_minutes: int | None = Field(alias="expectedEffortMinutes")
    demand_revision: int = Field(alias="demandRevision")


def _get_demand(
    db: Session, demand_id: uuid.UUID, principal: Principal, *, lock: bool = False
) -> Demand:
    query = select(Demand).where(
        Demand.id == demand_id,
        Demand.organization_id == principal.membership.organization_id,
        Demand.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    demand = db.scalar(query)
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    return demand


def _get_entry(
    db: Session,
    demand: Demand,
    entry_id: uuid.UUID,
    *,
    lock: bool = False,
) -> TimeEntry:
    query = select(TimeEntry).where(
        TimeEntry.id == entry_id,
        TimeEntry.organization_id == demand.organization_id,
        TimeEntry.demand_id == demand.id,
        TimeEntry.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    entry = db.scalar(query)
    if not entry:
        raise ApiError(404, "time_entry_not_found", "Apontamento de tempo não encontrado.")
    return entry


def can_change_time_entry(principal: Principal, entry: TimeEntry) -> bool:
    if entry.deleted_at:
        return False
    if entry.user_profile_id == principal.profile.id:
        return True
    permissions = set(principal.role.permissions if principal.role else [])
    return "*" in permissions or "demands:write" in permissions


def _entry_out(entry: TimeEntry, profile: UserProfile, principal: Principal) -> TimeEntryOut:
    return TimeEntryOut(
        id=entry.id,
        user_id=profile.id,
        user_name=profile.full_name,
        source=entry.source,
        state=entry.state,
        started_at=entry.started_at,
        ended_at=entry.ended_at,
        duration_minutes=entry.duration_minutes,
        note=entry.note,
        revision=entry.revision,
        can_edit=can_change_time_entry(principal, entry),
        created_at=entry.created_at,
    )


def _entry_profile(db: Session, entry: TimeEntry) -> UserProfile:
    profile = db.get(UserProfile, entry.user_profile_id)
    if not profile:
        raise ApiError(404, "time_entry_user_not_found", "Autor do apontamento não encontrado.")
    return profile


def _audit(principal: Principal, event_type: str, metadata: dict[str, object]) -> AuditEvent:
    return AuditEvent(
        organization_id=principal.membership.organization_id,
        actor_user_id=principal.profile.id,
        event_type=event_type,
        metadata_json=metadata,
    )


def _format_duration(minutes: int) -> str:
    hours, remaining = divmod(minutes, 60)
    if hours and remaining:
        return f"{hours}h {remaining}min"
    if hours:
        return f"{hours}h"
    return f"{remaining}min"


def _event(
    demand: Demand,
    principal: Principal,
    *,
    kind: str,
    summary: str,
    payload: dict[str, object],
) -> DemandUpdate:
    return DemandUpdate(
        demand_id=demand.id,
        created_by=principal.profile.id,
        kind=kind,
        summary=summary,
        payload=payload,
    )


def _summary(db: Session, demand: Demand, principal: Principal) -> TimeSummaryOut:
    rows = db.execute(
        select(TimeEntry, UserProfile)
        .join(UserProfile, UserProfile.id == TimeEntry.user_profile_id)
        .where(TimeEntry.demand_id == demand.id, TimeEntry.deleted_at.is_(None))
        .order_by(TimeEntry.started_at.desc())
    ).all()
    entries = [_entry_out(entry, profile, principal) for entry, profile in rows]
    completed = [entry for entry, _profile in rows if entry.state == "COMPLETED"]
    active = next(
        (
            _entry_out(entry, profile, principal)
            for entry, profile in rows
            if entry.state == "RUNNING" and entry.user_profile_id == principal.profile.id
        ),
        None,
    )
    return TimeSummaryOut(
        expected_effort_minutes=demand.expected_effort_minutes,
        total_minutes=sum(entry.duration_minutes or 0 for entry in completed),
        my_total_minutes=sum(
            entry.duration_minutes or 0
            for entry in completed
            if entry.user_profile_id == principal.profile.id
        ),
        active_timer=active,
        entries=entries,
        demand_revision=demand.revision,
    )


@router.get("/{demand_id}/time", response_model=TimeSummaryOut)
def get_time_summary(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> TimeSummaryOut:
    require_permission(principal, "demands:read")
    demand = _get_demand(db, demand_id, principal)
    return _summary(db, demand, principal)


@router.put(
    "/{demand_id}/time/estimate",
    response_model=TimeEstimateOut,
    dependencies=[Depends(require_csrf)],
)
def update_time_estimate(
    demand_id: uuid.UUID,
    payload: TimeEstimateUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> TimeEstimateOut:
    require_permission(principal, "demands:write")
    demand = _get_demand(db, demand_id, principal, lock=True)
    if demand.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "A demanda foi alterada. Atualize os dados.")
    previous = demand.expected_effort_minutes
    demand.expected_effort_minutes = payload.expected_effort_minutes
    demand.revision += 1
    demand.updated_at = utc_now()
    description = (
        _format_duration(payload.expected_effort_minutes)
        if payload.expected_effort_minutes
        else "não definido"
    )
    db.add(
        _event(
            demand,
            principal,
            kind="TIME_ESTIMATE_UPDATED",
            summary=f"Esforço previsto atualizado para {description}.",
            payload={
                "previousMinutes": previous,
                "expectedEffortMinutes": payload.expected_effort_minutes,
            },
        )
    )
    db.add(
        _audit(
            principal,
            "DEMAND_TIME_ESTIMATE_UPDATED",
            {
                "demandId": str(demand.id),
                "previousMinutes": previous,
                "expectedEffortMinutes": payload.expected_effort_minutes,
            },
        )
    )
    db.commit()
    return TimeEstimateOut(
        expected_effort_minutes=demand.expected_effort_minutes,
        demand_revision=demand.revision,
    )


@router.post(
    "/{demand_id}/time/entries",
    response_model=TimeEntryOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_manual_time_entry(
    demand_id: uuid.UUID,
    payload: ManualTimeEntryCreate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> TimeEntryOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    entry = TimeEntry(
        organization_id=demand.organization_id,
        demand_id=demand.id,
        user_profile_id=principal.profile.id,
        source="MANUAL",
        state="COMPLETED",
        started_at=payload.started_at,
        ended_at=payload.started_at + timedelta(minutes=payload.duration_minutes),
        duration_minutes=payload.duration_minutes,
        note=payload.note,
    )
    db.add(entry)
    db.flush()
    db.add(
        _event(
            demand,
            principal,
            kind="TIME_ENTRY_CREATED",
            summary=f"{_format_duration(payload.duration_minutes)} foram apontados na demanda.",
            payload={"timeEntryId": str(entry.id), "durationMinutes": payload.duration_minutes},
        )
    )
    db.add(
        _audit(
            principal,
            "TIME_ENTRY_CREATED",
            {
                "demandId": str(demand.id),
                "timeEntryId": str(entry.id),
                "durationMinutes": payload.duration_minutes,
            },
        )
    )
    db.commit()
    db.refresh(entry)
    return _entry_out(entry, principal.profile, principal)


@router.put(
    "/{demand_id}/time/entries/{entry_id}",
    response_model=TimeEntryOut,
    dependencies=[Depends(require_csrf)],
)
def update_time_entry(
    demand_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: TimeEntryEdit,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> TimeEntryOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    entry = _get_entry(db, demand, entry_id, lock=True)
    if not can_change_time_entry(principal, entry):
        raise ApiError(403, "time_entry_change_denied", "Você não pode editar este apontamento.")
    if entry.state != "COMPLETED":
        raise ApiError(409, "timer_still_running", "Pare o timer antes de editar o apontamento.")
    if entry.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O apontamento foi alterado. Atualize a lista.")
    previous_minutes = entry.duration_minutes
    changed_at = utc_now()
    entry.started_at = payload.started_at
    entry.ended_at = payload.started_at + timedelta(minutes=payload.duration_minutes)
    entry.duration_minutes = payload.duration_minutes
    entry.note = payload.note
    entry.revision += 1
    entry.updated_at = changed_at
    db.add(
        _event(
            demand,
            principal,
            kind="TIME_ENTRY_UPDATED",
            summary=f"Apontamento de tempo ajustado para {_format_duration(payload.duration_minutes)}.",
            payload={
                "timeEntryId": str(entry.id),
                "previousMinutes": previous_minutes,
                "durationMinutes": payload.duration_minutes,
            },
        )
    )
    db.add(
        _audit(
            principal,
            "TIME_ENTRY_UPDATED",
            {
                "demandId": str(demand.id),
                "timeEntryId": str(entry.id),
                "previousMinutes": previous_minutes,
                "durationMinutes": payload.duration_minutes,
            },
        )
    )
    db.commit()
    return _entry_out(entry, _entry_profile(db, entry), principal)


@router.delete(
    "/{demand_id}/time/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_time_entry(
    demand_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: TimeEntryDelete,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> None:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    entry = _get_entry(db, demand, entry_id, lock=True)
    if not can_change_time_entry(principal, entry):
        raise ApiError(403, "time_entry_change_denied", "Você não pode remover este apontamento.")
    if entry.state != "COMPLETED":
        raise ApiError(409, "timer_still_running", "Pare o timer antes de remover o apontamento.")
    if entry.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O apontamento foi alterado. Atualize a lista.")
    changed_at = utc_now()
    entry.deleted_at = changed_at
    entry.updated_at = changed_at
    entry.revision += 1
    db.add(
        _event(
            demand,
            principal,
            kind="TIME_ENTRY_REMOVED",
            summary="Um apontamento de tempo foi removido da demanda.",
            payload={"timeEntryId": str(entry.id)},
        )
    )
    db.add(
        _audit(
            principal,
            "TIME_ENTRY_REMOVED",
            {"demandId": str(demand.id), "timeEntryId": str(entry.id)},
        )
    )
    db.commit()


@router.post(
    "/{demand_id}/time/timer/start",
    response_model=TimeEntryOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def start_timer(
    demand_id: uuid.UUID,
    payload: TimerStart,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> TimeEntryOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    active = db.scalar(
        select(TimeEntry).where(
            TimeEntry.organization_id == demand.organization_id,
            TimeEntry.user_profile_id == principal.profile.id,
            TimeEntry.state == "RUNNING",
            TimeEntry.deleted_at.is_(None),
        )
    )
    if active:
        raise ApiError(409, "timer_already_running", "Você já possui um timer em andamento.")
    entry = TimeEntry(
        organization_id=demand.organization_id,
        demand_id=demand.id,
        user_profile_id=principal.profile.id,
        source="TIMER",
        state="RUNNING",
        started_at=utc_now(),
        note=payload.note,
    )
    try:
        db.add(entry)
        db.flush()
        db.add(
            _event(
                demand,
                principal,
                kind="TIMER_STARTED",
                summary="Timer iniciado na demanda.",
                payload={"timeEntryId": str(entry.id)},
            )
        )
        db.add(
            _audit(
                principal,
                "TIME_TIMER_STARTED",
                {"demandId": str(demand.id), "timeEntryId": str(entry.id)},
            )
        )
        db.commit()
        db.refresh(entry)
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            409, "timer_already_running", "Você já possui um timer em andamento."
        ) from exc
    return _entry_out(entry, principal.profile, principal)


@router.post(
    "/{demand_id}/time/timer/stop",
    response_model=TimeEntryOut,
    dependencies=[Depends(require_csrf)],
)
def stop_timer(
    demand_id: uuid.UUID,
    payload: TimerStop,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> TimeEntryOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    entry = db.scalar(
        select(TimeEntry)
        .where(
            TimeEntry.organization_id == demand.organization_id,
            TimeEntry.demand_id == demand.id,
            TimeEntry.user_profile_id == principal.profile.id,
            TimeEntry.state == "RUNNING",
            TimeEntry.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not entry:
        raise ApiError(404, "timer_not_found", "Não há timer ativo nesta demanda.")
    if entry.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O timer foi alterado. Atualize os dados.")
    ended_at = utc_now()
    duration_minutes = max(1, math.ceil((ended_at - entry.started_at).total_seconds() / 60))
    entry.state = "COMPLETED"
    entry.ended_at = ended_at
    entry.duration_minutes = duration_minutes
    entry.revision += 1
    entry.updated_at = ended_at
    db.add(
        _event(
            demand,
            principal,
            kind="TIMER_STOPPED",
            summary=f"Timer encerrado com {_format_duration(duration_minutes)}.",
            payload={"timeEntryId": str(entry.id), "durationMinutes": duration_minutes},
        )
    )
    db.add(
        _audit(
            principal,
            "TIME_TIMER_STOPPED",
            {
                "demandId": str(demand.id),
                "timeEntryId": str(entry.id),
                "durationMinutes": duration_minutes,
            },
        )
    )
    db.commit()
    return _entry_out(entry, principal.profile, principal)
