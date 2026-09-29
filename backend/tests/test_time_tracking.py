import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.time_tracking import (
    ManualTimeEntryCreate,
    TimeEstimateUpdate,
    TimerStart,
    TimerStop,
    can_change_time_entry,
    create_manual_time_entry,
    start_timer,
    stop_timer,
    update_time_estimate,
)
from app.auth.service import Principal
from app.models import (
    AppSession,
    AuditEvent,
    Demand,
    DemandUpdate,
    Membership,
    MembershipStatus,
    PermissionRole,
    TimeEntry,
    UserProfile,
    utc_now,
)


def _principal(*, code: str = "collaborator", profile_id: uuid.UUID | None = None) -> Principal:
    organization_id = uuid.uuid4()
    profile = UserProfile(
        id=profile_id or uuid.uuid4(),
        auth_user_id=uuid.uuid4(),
        email=f"{code}@example.com",
        full_name=code.title(),
    )
    membership = Membership(
        id=uuid.uuid4(),
        organization_id=organization_id,
        user_profile_id=profile.id,
        status=MembershipStatus.ACTIVE,
    )
    permissions = (
        ["demands:read", "demands:write"]
        if code == "coordinator"
        else ["demands:read", "demands:work"]
    )
    role = PermissionRole(
        id=uuid.uuid4(),
        organization_id=organization_id,
        code=code,
        name=code.title(),
        permissions=permissions,
    )
    return Principal(MagicMock(spec=AppSession), profile, membership, role)


def _demand(principal: Principal) -> Demand:
    return Demand(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        public_id="DMD-2026-000301",
        title="Campanha institucional",
        status="WAITING_EXECUTION",
        priority="NORMAL",
        source="interface",
        revision=3,
        created_by=principal.profile.id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def _entry(principal: Principal, demand: Demand, *, state: str = "COMPLETED") -> TimeEntry:
    started_at = utc_now() - timedelta(minutes=30)
    return TimeEntry(
        id=uuid.uuid4(),
        organization_id=demand.organization_id,
        demand_id=demand.id,
        user_profile_id=principal.profile.id,
        source="TIMER" if state == "RUNNING" else "MANUAL",
        state=state,
        started_at=started_at,
        ended_at=None if state == "RUNNING" else started_at + timedelta(minutes=30),
        duration_minutes=None if state == "RUNNING" else 30,
        note="Produção",
        revision=1,
        created_at=started_at,
        updated_at=started_at,
    )


def _assign_entry_database_values(db: MagicMock) -> TimeEntry:
    entry = next(
        value
        for value in (call.args[0] for call in db.add.call_args_list)
        if isinstance(value, TimeEntry)
    )
    entry.id = uuid.uuid4()
    entry.revision = 1
    entry.created_at = utc_now()
    entry.updated_at = entry.created_at
    return entry


def test_manual_entry_persists_duration_timeline_and_audit() -> None:
    principal = _principal()
    demand = _demand(principal)
    db = MagicMock(spec=Session)
    db.scalar.return_value = demand
    db.flush.side_effect = lambda: _assign_entry_database_values(db)
    started_at = utc_now() - timedelta(hours=2)

    result = create_manual_time_entry(
        demand.id,
        ManualTimeEntryCreate(startedAt=started_at, durationMinutes=75, note="  Roteiro  "),
        principal,
        db,
    )

    assert result.duration_minutes == 75
    assert result.note == "Roteiro"
    assert result.ended_at == started_at + timedelta(minutes=75)
    added = [call.args[0] for call in db.add.call_args_list]
    assert any(
        isinstance(value, DemandUpdate)
        and value.kind == "TIME_ENTRY_CREATED"
        and "1h 15min" in value.summary
        for value in added
    )
    assert any(
        isinstance(value, AuditEvent) and value.event_type == "TIME_ENTRY_CREATED"
        for value in added
    )
    db.commit.assert_called_once()


def test_only_author_or_coordinator_can_change_entry() -> None:
    author = _principal()
    demand = _demand(author)
    entry = _entry(author, demand)
    colleague = _principal()
    coordinator = _principal(code="coordinator")

    assert can_change_time_entry(author, entry)
    assert not can_change_time_entry(colleague, entry)
    assert can_change_time_entry(coordinator, entry)


def test_start_timer_rejects_another_active_timer_for_user() -> None:
    principal = _principal()
    demand = _demand(principal)
    active = _entry(principal, demand, state="RUNNING")
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [demand, active]

    with pytest.raises(ApiError) as caught:
        start_timer(demand.id, TimerStart(note="Execução"), principal, db)

    assert caught.value.status_code == 409
    assert caught.value.code == "timer_already_running"
    db.add.assert_not_called()


def test_start_and_stop_timer_use_minimum_one_minute_and_register_events() -> None:
    principal = _principal()
    demand = _demand(principal)
    create_db = MagicMock(spec=Session)
    create_db.scalar.side_effect = [demand, None]
    create_db.flush.side_effect = lambda: _assign_entry_database_values(create_db)

    started = start_timer(demand.id, TimerStart(note="Execução"), principal, create_db)
    entry = next(
        value
        for value in (call.args[0] for call in create_db.add.call_args_list)
        if isinstance(value, TimeEntry)
    )
    assert started.state == "RUNNING"
    assert entry.duration_minutes is None
    assert any(
        isinstance(call.args[0], DemandUpdate) and call.args[0].kind == "TIMER_STARTED"
        for call in create_db.add.call_args_list
    )

    entry.started_at = utc_now()
    stop_db = MagicMock(spec=Session)
    stop_db.scalar.side_effect = [demand, entry]
    stopped = stop_timer(
        demand.id,
        TimerStop(expectedRevision=entry.revision),
        principal,
        stop_db,
    )

    assert stopped.state == "COMPLETED"
    assert stopped.duration_minutes == 1
    assert entry.ended_at is not None
    assert any(
        isinstance(call.args[0], AuditEvent) and call.args[0].event_type == "TIME_TIMER_STOPPED"
        for call in stop_db.add.call_args_list
    )
    stop_db.commit.assert_called_once()


def test_estimate_requires_current_demand_revision_and_updates_timeline() -> None:
    principal = _principal(code="coordinator")
    demand = _demand(principal)
    db = MagicMock(spec=Session)
    db.scalar.return_value = demand

    result = update_time_estimate(
        demand.id,
        TimeEstimateUpdate(expectedEffortMinutes=180, expectedRevision=3),
        principal,
        db,
    )

    assert result.expected_effort_minutes == 180
    assert result.demand_revision == 4
    assert any(
        isinstance(call.args[0], DemandUpdate) and call.args[0].kind == "TIME_ESTIMATE_UPDATED"
        for call in db.add.call_args_list
    )

    stale_db = MagicMock(spec=Session)
    stale_db.scalar.return_value = demand
    with pytest.raises(ApiError) as caught:
        update_time_estimate(
            demand.id,
            TimeEstimateUpdate(expectedEffortMinutes=240, expectedRevision=3),
            principal,
            stale_db,
        )
    assert caught.value.code == "revision_conflict"
