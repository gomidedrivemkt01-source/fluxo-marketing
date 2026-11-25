import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from test_management_postgres import setup as setup  # noqa: F401

from app.api.analytics import analytics_report
from app.api.demands import record_stage_visit_transition
from app.api.errors import ApiError
from app.api.notifications import PolicyUpdate, get_policy, inbox, save_policy
from app.auth.service import Principal
from app.models import AuditEvent, DemandStageVisit, DemandUpdate, PermissionRole

pytestmark = pytest.mark.skipif(
    not os.environ.get("FM_MANAGEMENT_TEST_DSN"), reason="Local disposable PostgreSQL required"
)


def own(s, number=1):
    role = PermissionRole(
        organization_id=s.org.id,
        code="collaborator",
        name="Colaborador",
        permissions=["demands:read"],
    )
    return Principal(MagicMock(), s.people[number][0], s.people[number][1], role)


def read(s, principal=None, assignee_id=None):
    return analytics_report(
        days=30,
        start_date=None,
        end_date=None,
        assignee_id=assignee_id,
        principal=principal or s.principal,
        db=s.db,
    )


def complete_with_handoffs(s, initial_person=1, initial_inferred=False):
    card = s.cards[0]
    card.current_assignee_id = s.people[initial_person][0].id
    base = datetime.now(UTC) - timedelta(days=3)
    initial = s.db.scalar(
        select(DemandStageVisit).where(
            DemandStageVisit.demand_id == card.id, DemandStageVisit.left_at.is_(None)
        )
    )
    if initial is None:
        record_stage_visit_transition(
            s.db,
            card,
            actor_id=s.people[0][0].id,
            from_stage_id=None,
            to_stage_id=s.stages[0].id,
            action="START",
            moved_at=base - timedelta(hours=4),
        )
        s.db.flush()
        initial = s.db.scalar(
            select(DemandStageVisit).where(
                DemandStageVisit.demand_id == card.id, DemandStageVisit.left_at.is_(None)
            )
        )
    initial.entered_at = base - timedelta(hours=4)
    initial.inferred = initial_inferred
    initial.assignee_id = s.people[initial_person][0].id
    s.stages[0].sla_hours = 24
    for index, stage in enumerate(s.stages):
        target = s.stages[index + 1] if index < 2 else None
        card.current_stage_id = target.id if target else stage.id
        card.current_assignee_id = s.people[2 if index >= 1 else 1][0].id
        record_stage_visit_transition(
            s.db,
            card,
            actor_id=s.people[0][0].id,
            from_stage_id=stage.id,
            to_stage_id=target.id if target else None,
            action="ADVANCE" if target else "COMPLETE",
            moved_at=base + timedelta(days=index),
        )
        s.db.flush()
    card.status = "COMPLETED"
    card.archived_at = datetime.now(UTC)
    s.db.add(
        DemandUpdate(
            demand_id=card.id,
            created_by=s.people[0][0].id,
            kind="DEMAND_COMPLETED",
            summary="Fim do fluxo",
            created_at=base + timedelta(days=2),
            payload={"action": "advance", "fromStageId": str(s.stages[-1].id)},
        )
    )
    s.db.flush()


def test_scoped_analytics_keeps_past_contributor_after_reassignment_and_archive(setup):
    s = setup
    complete_with_handoffs(s)
    result = read(s)
    assert result["summary"]["confirmedDeliveries"] == 2
    assert result["summary"]["completedCards"] == 1
    result = read(s, own(s))
    assert result["scope"] == "person"
    assert result["scopeProfileId"] == str(s.people[1][0].id)
    assert result["summary"]["confirmedDeliveries"] == 1
    assert result["summary"]["completedCards"] == 1
    assert all(row["profileId"] == str(s.people[1][0].id) for row in result["people"])
    with pytest.raises(ApiError) as denied:
        read(s, own(s), s.people[2][0].id)
    assert denied.value.status_code == 403
    coordinator = Principal(
        s.principal.session,
        s.principal.profile,
        s.principal.membership,
        PermissionRole(code="coordinator", permissions=["demands:read"]),
    )
    assert read(s, coordinator)["scope"] == "team"


def test_exit_freezes_historical_name_deadline_and_action(setup):
    s = setup
    complete_with_handoffs(s)
    visits = s.db.scalars(
        select(DemandStageVisit)
        .where(DemandStageVisit.demand_id == s.cards[0].id)
        .order_by(DemandStageVisit.visit_number)
    ).all()
    snapshot = visits[0].acceptance_snapshot
    assert snapshot["exitAction"] == "ADVANCE"
    assert snapshot["demandDeadlineAt"] == s.cards[0].deadline_at.isoformat()
    assert snapshot["stageName"] == s.stages[0].name
    s.stages[0].name = "Alterado depois"
    s.stages[0].sla_hours = 999
    s.db.flush()
    assert visits[0].acceptance_snapshot == snapshot
    assert read(s)["stages"][0]["name"] != s.stages[0].name


def test_policy_revision_admin_guard_and_audit(setup):
    s = setup
    original = get_policy(s.principal, s.db)
    assert original.warning_days == 7 and original.revision == 0
    payload = PolicyUpdate(warningDays=5, expectedRevision=0)
    saved = save_policy(payload, s.principal, s.db)
    assert saved.warning_days == 5 and saved.revision == 1
    assert s.db.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == s.org.id,
            AuditEvent.event_type == "NOTIFICATION_POLICY_UPDATED",
        )
    )
    with pytest.raises(ApiError) as stale:
        save_policy(payload, s.principal, s.db)
    assert stale.value.status_code == 409
    with pytest.raises(ApiError) as denied:
        save_policy(PolicyUpdate(expectedRevision=1), own(s), s.db)
    assert denied.value.status_code == 403


def test_notification_former_participants_and_policy_toggle(setup):
    s = setup
    card = s.cards[0]
    record_stage_visit_transition(
        s.db,
        card,
        actor_id=s.people[0][0].id,
        from_stage_id=None,
        to_stage_id=s.stages[0].id,
        action="START",
        moved_at=datetime.now(UTC) - timedelta(days=2),
    )
    card.deadline_at = datetime.now(UTC) + timedelta(days=3)
    card.current_assignee_id = s.people[2][0].id
    s.db.flush()
    result = inbox(own(s), s.db)
    assert str(card.id) in {item["id"] for item in result["items"]}
    item = next(item for item in result["items"] if item["id"] == str(card.id))
    assert item["participating"] is True
    saved = save_policy(
        PolicyUpdate(includeParticipating=False, expectedRevision=0), s.principal, s.db
    )
    assert str(card.id) not in {item["id"] for item in inbox(own(s), s.db)["items"]}
    save_policy(PolicyUpdate(enabled=False, expectedRevision=saved.revision), s.principal, s.db)
    assert inbox(own(s), s.db)["items"] == []


def test_past_contributor_with_inferred_entry_and_real_exit_remains_in_own_scope(setup):
    s = setup
    complete_with_handoffs(s, initial_person=3, initial_inferred=True)
    result = read(s, own(s, 3))
    assert result["summary"]["confirmedDeliveries"] == 1
    assert result["summary"]["completedCards"] == 1
    assert result["stages"] == []  # the uncertain entry cannot measure elapsed time
    assert result["people"][0]["profileId"] == str(s.people[3][0].id)
