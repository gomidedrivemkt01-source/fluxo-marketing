import uuid
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.models import Demand, DemandStageVisit, DemandUpdate, TimeEntry, WorkflowVersion
from app.personal_performance import build_personal_performance

NOW = datetime(2026, 11, 26, 18, tzinfo=UTC)
ZONE = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def data():
    own, peer, org, workflow, category = [uuid.uuid4() for _ in range(5)]
    stage_ids = [uuid.uuid4() for _ in range(3)]
    version = WorkflowVersion(
        id=uuid.uuid4(),
        workflow_id=workflow,
        definition={
            "stages": [
                {"id": str(stage_ids[0]), "name": "Criação", "position": 1},
                {"id": str(stage_ids[1]), "name": "Revisão e aprovação", "position": 2},
                {"id": str(stage_ids[2]), "name": "Publicação", "position": 3},
            ]
        },
    )
    return SimpleNamespace(
        own=own,
        peer=peer,
        org=org,
        workflow=workflow,
        category=category,
        stages=stage_ids,
        version=version,
        cards=[],
        visits=[],
        events=[],
        entries=[],
    )


def card(d, done=False):
    value = Demand(
        id=uuid.uuid4(),
        organization_id=d.org,
        created_by=d.peer,
        title="Material sintético",
        public_id=f"QA-{len(d.cards)}",
        status="COMPLETED" if done else "IN_PROGRESS",
        workflow_id=d.workflow,
        workflow_version_id=d.version.id,
        category_id=d.category,
        current_assignee_id=d.own,
        created_at=NOW - timedelta(days=40),
    )
    d.cards.append(value)
    return value


def visit(d, c, stage, number, entered, left=None, person=None, action="ADVANCE", exit=None):
    value = DemandStageVisit(
        id=uuid.uuid4(),
        organization_id=d.org,
        demand_id=c.id,
        workflow_stage_id=d.stages[stage],
        workflow_version_id=d.version.id,
        visit_number=number,
        entered_at=entered,
        left_at=left,
        assignee_id=person or d.own,
        entered_by=d.peer,
        left_by=d.peer,
        action=action,
        inferred=False,
        acceptance_snapshot={
            "exitAction": exit or ("COMPLETE" if stage == 2 else "ADVANCE"),
            "stageName": d.version.definition["stages"][stage]["name"],
        },
    )
    d.visits.append(value)
    return value


def complete(d, c, own_at=NOW - timedelta(hours=4), finished=NOW - timedelta(hours=1)):
    visit(d, c, 0, 1, own_at - timedelta(hours=1), own_at)
    visit(d, c, 1, 2, own_at, finished - timedelta(minutes=30), person=d.peer)
    visit(d, c, 2, 3, finished - timedelta(minutes=30), finished, person=d.peer)
    d.events.append(
        DemandUpdate(
            id=uuid.uuid4(),
            demand_id=c.id,
            created_by=d.peer,
            kind="DEMAND_COMPLETED",
            created_at=finished,
            payload={"action": "advance", "fromStageId": str(d.stages[-1])},
        )
    )


def entry(d, c, start, end, minutes, source="TIMER", state="COMPLETED", owner=None):
    value = TimeEntry(
        id=uuid.uuid4(),
        organization_id=d.org,
        demand_id=c.id,
        user_profile_id=owner or d.own,
        source=source,
        state=state,
        started_at=start,
        ended_at=end,
        duration_minutes=minutes,
        deleted_at=None,
        created_at=start,
    )
    d.entries.append(value)
    return value


def event(d, e, kind, at, exact=None):
    d.events.append(
        DemandUpdate(
            id=uuid.uuid4(),
            demand_id=e.demand_id,
            created_by=d.own,
            kind=kind,
            created_at=at,
            payload={"timeEntryId": str(e.id), **({"at": exact.isoformat()} if exact else {})},
        )
    )


def report(d, start=None, end=None, **kwargs):
    return build_personal_performance(
        profile_id=d.own,
        cards=d.cards,
        visits=d.visits,
        events=d.events,
        entries=d.entries,
        versions={d.version.id: d.version},
        start=start or datetime(2026, 11, 26, 3, tzinfo=UTC),
        end=end or datetime(2026, 11, 27, 3, tzinfo=UTC),
        now=NOW,
        zone=ZONE,
        **kwargs,
    )


def test_pause_and_resume_do_not_draw_or_charge_the_gap(data):
    d = data
    c = card(d)
    e = entry(d, c, NOW - timedelta(hours=2), NOW - timedelta(hours=1), 120)
    event(d, e, "TIMER_STARTED", NOW - timedelta(hours=5))
    event(d, e, "TIMER_PAUSED", NOW - timedelta(hours=4))
    event(d, e, "TIMER_RESUMED", e.started_at)
    event(d, e, "TIMER_STOPPED", e.ended_at)
    r = report(d)
    assert r["summary"]["recordedMinutes"] == 120
    assert r["summary"]["timerStarts"] == 1 and r["summary"]["timerResumes"] == 1
    assert len(r["segments"]) == 2 and sum(s["minutes"] for s in r["segments"]) == 120
    assert r["summary"]["coverageMinutes"] == 120


def test_parallel_timers_preserve_sum_but_union_the_clock_coverage(data):
    d = data
    c = card(d)
    for offset in [0, 30]:
        start = NOW - timedelta(hours=3) + timedelta(minutes=offset)
        e = entry(d, c, start, start + timedelta(hours=1), 60)
        event(d, e, "TIMER_STARTED", e.started_at)
        event(d, e, "TIMER_STOPPED", e.ended_at)
    r = report(d)
    assert r["summary"]["recordedMinutes"] == 120 and r["summary"]["coverageMinutes"] == 90
    assert all(gap["startedAt"] >= NOW - timedelta(hours=1, minutes=30) for gap in r["gaps"])


def test_midnight_uses_the_profile_date_and_clips_both_sources(data):
    d = data
    c = card(d)
    a = datetime(2026, 11, 26, 2, tzinfo=UTC)
    b = a + timedelta(hours=2)
    e = entry(d, c, a, b, 120)
    event(d, e, "TIMER_STARTED", a)
    event(d, e, "TIMER_STOPPED", b)
    entry(d, c, a + timedelta(minutes=30), b - timedelta(minutes=30), 60, source="MANUAL")
    r = report(d)
    assert r["summary"]["recordedMinutes"] == 90
    assert r["summary"]["timerStarts"] == 0
    assert all(s["date"] == "2026-11-26" and s["startMinute"] >= 0 for s in r["segments"])


def test_running_and_paused_are_pending_not_launched(data):
    d = data
    c = card(d)
    e = entry(d, c, NOW - timedelta(hours=1), None, 30, state="RUNNING")
    event(d, e, "TIMER_STARTED", NOW - timedelta(hours=3))
    event(d, e, "TIMER_PAUSED", NOW - timedelta(hours=2, minutes=30))
    event(d, e, "TIMER_RESUMED", e.started_at)
    r = report(d)
    assert r["summary"]["recordedMinutes"] == 0 and r["summary"]["pendingMinutes"] == 90
    assert len(r["segments"]) == 2 and r["segments"][-1]["running"]


def test_missing_trace_is_reported_without_inventing_a_timer(data):
    d = data
    c = card(d)
    entry(d, c, NOW - timedelta(hours=2), NOW - timedelta(hours=1), 60)
    r = report(d)
    assert r["summary"]["recordedMinutes"] == 60 and not r["segments"]
    assert r["quality"]["unlocatedMinutes"] == 60 and r["quality"]["entriesWithoutTrace"] == 1


def test_adjustments_use_the_supplied_interval_without_claiming_timer_coverage(data):
    d = data
    c = card(d)
    e = entry(d, c, NOW - timedelta(hours=1), NOW - timedelta(minutes=30), 30)
    event(d, e, "TIMER_STARTED", NOW - timedelta(hours=4))
    event(d, e, "TIMER_STOPPED", NOW - timedelta(hours=3))
    event(d, e, "TIME_ENTRY_UPDATED", NOW)
    r = report(d)
    assert r["summary"]["recordedMinutes"] == 30 and r["quality"]["adjustedEntries"] == 1
    assert [s["kind"] for s in r["segments"]] == ["adjusted"]


def test_delivery_cohort_is_unique_and_follows_later_final_completion(data):
    d = data
    c = card(d, done=True)
    yesterday = NOW - timedelta(days=1, hours=3)
    complete(d, c, own_at=yesterday)
    r = report(
        d, start=datetime(2026, 11, 25, 3, tzinfo=UTC), end=datetime(2026, 11, 26, 3, tzinfo=UTC)
    )
    assert r["summary"]["stageAdvances"] == 1 and r["summary"]["deliveredCards"] == 1
    assert r["summary"]["completedAfterDelivery"] == 1
    assert r["approval"]["approvalRate"] == 100 and r["approval"]["counts"]["pending"] == 0
    c.status = "IN_PROGRESS"
    r = report(
        d, start=datetime(2026, 11, 25, 3, tzinfo=UTC), end=datetime(2026, 11, 26, 3, tzinfo=UTC)
    )
    assert r["summary"]["completedAfterDelivery"] == 0


def test_several_stages_same_person_do_not_inflate_cards_or_use_button_actor(data):
    d = data
    c = card(d, done=True)
    complete(d, c)
    d.visits[1].assignee_id = d.own
    r = report(d)
    assert r["summary"]["stageAdvances"] == 2 and r["summary"]["deliveredCards"] == 1
    assert r["approval"]["approvalRate"] is None  # peer-independent approval is absent


def test_pending_approval_is_not_assumed_approved(data):
    d = data
    c = card(d)
    at = NOW - timedelta(hours=2)
    visit(d, c, 0, 1, at - timedelta(hours=1), at)
    visit(d, c, 1, 2, at, person=d.peer)
    r = report(d)
    assert r["approval"]["counts"] == {"approved": 0, "rework": 0, "pending": 1}
    assert r["approval"]["approvalRate"] is None


def test_return_then_resubmit_counts_one_reworked_stage_and_two_advances(data):
    d = data
    c = card(d)
    at = NOW - timedelta(hours=5)
    visit(d, c, 0, 1, at - timedelta(hours=1), at)
    visit(d, c, 1, 2, at, at + timedelta(hours=1), person=d.peer, exit="RETURN")
    v = visit(d, c, 0, 3, at + timedelta(hours=1), at + timedelta(hours=2), action="RETURN")
    v.reason = "Corrigir a legenda"
    visit(d, c, 1, 4, at + timedelta(hours=2), at + timedelta(hours=3), person=d.peer)
    r = report(d)
    assert r["summary"]["returns"] == 1 and r["summary"]["stageAdvances"] == 2
    assert r["summary"]["deliveredCards"] == 1
    assert r["approval"]["counts"] == {"approved": 0, "rework": 1, "pending": 0}
    assert r["approval"]["reworkRate"] == 100
    assert r["returns"][0]["reason"] == "Corrigir a legenda"


def test_inferred_reassignment_and_skip_do_not_count_as_deliveries(data):
    d = data
    c = card(d)
    for i, action in enumerate(["REASSIGN", "SKIP", "ADVANCE"]):
        v = visit(
            d, c, 0, i + 1, NOW - timedelta(hours=4 - i), NOW - timedelta(hours=3 - i), exit=action
        )
        if action == "ADVANCE":
            v.inferred = True
    assert report(d)["summary"]["stageAdvances"] == 0


def test_gap_alerts_respect_window_and_do_not_assume_time_before_first_record(data):
    d = data
    c = card(d)
    for hour in [9, 13]:
        start = datetime(2026, 11, 26, hour + 3, tzinfo=UTC)
        entry(d, c, start, start + timedelta(hours=1), 60, source="MANUAL")
    r = report(d, gap_minutes=90, day_start=time(8), day_end=time(18))
    assert len(r["gaps"]) == 1 and r["gaps"][0]["minutes"] == 180
    assert not report(d, gap_minutes=90, day_start=time(13), day_end=time(18))["gaps"]


@pytest.mark.parametrize(
    "samples,minutes,expected",
    [(7, 120, None), (8, 120, "above"), (8, 30, "below"), (8, 65, "typical")],
)
def test_personal_reference_requires_eight_prior_comparable_closed_cards(
    data, samples, minutes, expected
):
    d = data
    for i in range(samples):
        c = card(d, done=True)
        finished = NOW - timedelta(days=i + 1)
        complete(d, c, own_at=finished - timedelta(hours=2), finished=finished)
        entry(
            d, c, finished - timedelta(hours=3), finished - timedelta(hours=2), 60, source="MANUAL"
        )
    focal = card(d, done=True)
    complete(d, focal)
    entry(
        d,
        focal,
        NOW - timedelta(hours=6),
        NOW - timedelta(hours=6) + timedelta(minutes=minutes),
        minutes,
        source="MANUAL",
    )
    r = report(d)
    assert (r["comparisons"][0]["outcome"] if r["comparisons"] else None) == expected
    if expected:
        assert r["comparisons"][0]["sampleCards"] == 8


def test_other_persons_time_is_excluded_and_deleted_entries_stay_excluded(data):
    d = data
    c = card(d)
    entry(d, c, NOW - timedelta(hours=1), NOW, 60, source="MANUAL", owner=d.peer)
    e = entry(d, c, NOW - timedelta(hours=1), NOW, 60, source="MANUAL")
    e.deleted_at = NOW
    assert report(d)["summary"]["recordedMinutes"] == 0


def test_manual_completion_without_terminal_evidence_does_not_confirm_the_cohort(data):
    d = data
    c = card(d, done=True)
    at = NOW - timedelta(hours=2)
    visit(d, c, 0, 1, at - timedelta(hours=1), at)
    visit(d, c, 1, 2, at, person=d.peer)
    d.events.append(
        DemandUpdate(
            id=uuid.uuid4(),
            demand_id=c.id,
            created_by=d.peer,
            kind="DEMAND_COMPLETED",
            created_at=NOW,
            payload={"status": "COMPLETED"},
        )
    )
    r = report(d)
    assert r["summary"]["completedAfterDelivery"] == 0
    assert r["summary"]["awaitingFinal"] == 1
    assert r["approval"]["counts"]["pending"] == 1


def test_partial_timer_history_preserves_duration_without_guessing_the_pause(data):
    d = data
    c = card(d)
    e = entry(d, c, NOW - timedelta(hours=3), NOW - timedelta(hours=1), 60)
    event(d, e, "TIMER_STARTED", e.started_at)
    event(d, e, "TIMER_STOPPED", e.ended_at)
    r = report(d)
    assert r["summary"]["recordedMinutes"] == 60 and not r["segments"]
    assert r["quality"]["unlocatedMinutes"] == 60


def test_timer_start_uses_exact_event_timestamp_at_midnight(data):
    d = data
    c = card(d)
    a = datetime(2026, 11, 26, 2, 59, 59, tzinfo=UTC)
    b = a + timedelta(minutes=20)
    e = entry(d, c, a, b, 20)
    event(d, e, "TIMER_STARTED", a + timedelta(seconds=2), exact=a)
    event(d, e, "TIMER_STOPPED", b)
    r = report(d)
    assert r["summary"]["timerStarts"] == 0
    assert r["summary"]["recordedMinutes"] == 20
