import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from test_management_postgres import setup as setup

from app.api.daily_imports import apply_proposal
from app.api.demands import (
    DemandEdit,
    DemandWorkflowAction,
    apply_workflow_action,
    get_demand,
    list_demands,
    update_demand,
)
from app.api.errors import ApiError
from app.api.governance import governance_overview, restore_demand
from app.api.reports import operational_report
from app.api.time_tracking import TimerStart, start_timer
from app.demand_lifecycle import set_demand_status
from app.models import Comment, DailyImportItem, DemandStageInstance, DemandUpdate, TimeEntry

pytestmark = pytest.mark.skipif(
    not os.environ.get("FM_MANAGEMENT_TEST_DSN"), reason="Requires disposable local PostgreSQL"
)


def edit(card, status):
    return DemandEdit(
        title=card.title,
        description=card.description,
        companyId=card.primary_company_id,
        categoryId=card.category_id,
        priority=card.priority,
        status=status,
        deadlineAt=card.deadline_at,
        expectedRevision=card.revision,
        assigneeId=card.current_assignee_id,
        stageId=card.current_stage_id,
        workflowId=card.workflow_id,
    )


def publish(s):
    s.source.lifecycle_state = "PUBLISHED"
    s.default.lifecycle_state = "PUBLISHED"
    s.db.flush()


def test_legacy_completed_cards_live_in_archive_not_operational_listing(setup):
    s = setup
    publish(s)
    legacy = s.cards[2]
    assert legacy.status == "COMPLETED" and legacy.archived_at is None
    assert legacy.id not in {item.id for item in list_demands(None, s.principal, s.db)}
    archived = governance_overview(s.principal, s.db)["archivedDemands"]
    assert str(legacy.id) in {item["id"] for item in archived}
    assert get_demand(legacy.id, s.principal, s.db).id == legacy.id
    assert legacy.archived_at is None  # Reads never perform hidden data migrations.


def test_edit_completion_archives_preserves_metrics_and_can_reopen(setup):
    s = setup
    publish(s)
    card = s.cards[0]
    entry = TimeEntry(
        organization_id=s.org.id,
        demand_id=card.id,
        user_profile_id=s.principal.profile.id,
        source="MANUAL",
        state="COMPLETED",
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        duration_minutes=45,
    )
    s.db.add(entry)
    s.db.flush()
    result = update_demand(card.id, edit(card, "COMPLETED"), s.principal, s.db)
    assert result.status == "COMPLETED" and card.archived_at is not None
    assert card.id not in {item.id for item in list_demands(None, s.principal, s.db)}
    assert s.db.get(Comment, s.comment.id).content == "Comentário histórico"
    assert s.db.get(TimeEntry, entry.id).duration_minutes == 45
    kinds = list(s.db.scalars(select(DemandUpdate.kind).where(DemandUpdate.demand_id == card.id)))
    assert kinds.count("DEMAND_COMPLETED") == 1 and kinds.count("DEMAND_ARCHIVED") == 1
    report = operational_report(30, None, None, None, s.principal, s.db)
    assert report.summary.completed_demands == 2 and report.summary.tracked_minutes == 45
    update_demand(card.id, edit(card, "IN_PROGRESS"), s.principal, s.db)
    assert card.archived_at is None
    assert card.id in {item.id for item in list_demands(None, s.principal, s.db)}


def test_last_workflow_stage_completion_archives_once(setup):
    s = setup
    publish(s)
    card = s.cards[0]
    card.current_stage_id = s.stages[-1].id
    for instance in s.db.scalars(
        select(DemandStageInstance).where(DemandStageInstance.demand_id == card.id)
    ):
        instance.state = (
            "current" if instance.workflow_stage_id == card.current_stage_id else "completed"
        )
    s.db.flush()
    apply_workflow_action(
        card.id,
        DemandWorkflowAction(action="advance", expectedRevision=card.revision),
        s.principal,
        s.db,
    )
    assert card.status == "COMPLETED" and card.archived_at is not None
    kinds = list(s.db.scalars(select(DemandUpdate.kind).where(DemandUpdate.demand_id == card.id)))
    assert kinds.count("DEMAND_COMPLETED") == 1
    assert kinds.count("DEMAND_ARCHIVED") == 1


def test_daily_status_completion_and_restoration_follow_lifecycle(setup):
    s = setup
    card = s.cards[0]
    item = DailyImportItem(summary="Conclusão registrada na Daily")
    # No import persistence is needed to exercise the proposal's status transition.
    item.id = None
    apply_proposal(
        s.db, s.principal, card, item, {"type": "SET_STATUS", "payload": {"value": "COMPLETED"}}
    )
    s.db.flush()
    assert card.archived_at is not None
    restore_demand(card.id, s.principal, s.db)
    assert card.status == "WAITING_EXECUTION" and card.archived_at is None
    assert s.db.get(Comment, s.comment.id) is not None


@pytest.mark.parametrize("state", ["RUNNING", "PAUSED"])
def test_open_timer_blocks_completion_without_losing_tracking(setup, state):
    s = setup
    card = s.cards[0]
    entry = TimeEntry(
        organization_id=s.org.id,
        demand_id=card.id,
        user_profile_id=s.principal.profile.id,
        source="TIMER",
        state=state,
        timer_slot=1,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC) if state == "PAUSED" else None,
        duration_minutes=1 if state == "PAUSED" else None,
    )
    s.db.add(entry)
    s.db.flush()
    with pytest.raises(ApiError) as caught:
        set_demand_status(s.db, card, "COMPLETED", actor_id=s.principal.profile.id, source="test")
    assert caught.value.code == "active_timer_requires_closure"
    assert card.status == "IN_PROGRESS" and card.archived_at is None
    assert entry.state == state


def test_completed_card_cannot_start_new_timer(setup):
    s = setup
    with pytest.raises(ApiError) as caught:
        start_timer(s.cards[2].id, TimerStart(), s.principal, s.db)
    assert caught.value.code == "demand_archived"
