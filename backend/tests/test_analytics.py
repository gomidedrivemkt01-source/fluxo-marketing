import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.analytics import build_analytics, stage_exit
from app.api.notifications import PolicyOut, alert_reasons
from app.models import Demand, DemandStageVisit, DemandUpdate, TimeEntry, WorkflowVersion

NOW = datetime(2026, 11, 25, 15, tzinfo=UTC)


@pytest.fixture
def history():
    a, b, actor, org, card_id, version_id = [uuid.uuid4() for _ in range(6)]
    stages = [uuid.uuid4() for _ in range(3)]
    version = WorkflowVersion(
        id=version_id,
        workflow_id=uuid.uuid4(),
        definition={
            "stages": [
                {"id": str(identifier), "position": position}
                for position, identifier in enumerate(stages)
            ]
        },
    )
    card = Demand(
        id=card_id,
        organization_id=org,
        public_id="TEST-1",
        title="Conteúdo",
        created_by=actor,
        created_at=NOW - timedelta(days=20),
        status="COMPLETED",
        current_assignee_id=b,
        deadline_at=NOW + timedelta(days=1),
    )
    visits = []
    for i, person in enumerate([a, a, b]):
        end = NOW - timedelta(days=4 - i)
        visits.append(
            DemandStageVisit(
                id=uuid.uuid4(),
                organization_id=org,
                demand_id=card_id,
                workflow_version_id=version_id,
                workflow_stage_id=stages[i],
                visit_number=i + 1,
                action="START" if i == 0 else "ADVANCE",
                entered_at=end - timedelta(hours=12),
                left_at=end,
                assignee_id=person,
                entered_by=actor,
                left_by=actor,
                inferred=False,
                acceptance_snapshot={
                    "exitAction": "COMPLETE" if i == 2 else "ADVANCE",
                    "exitStageId": str(stages[i + 1]) if i < 2 else None,
                    "stageName": f"Etapa {i}",
                    "slaHours": 24,
                    "demandDeadlineAt": (NOW + timedelta(days=1)).isoformat(),
                },
            )
        )
    event = DemandUpdate(
        id=uuid.uuid4(),
        demand_id=card_id,
        created_by=actor,
        kind="DEMAND_COMPLETED",
        created_at=visits[-1].left_at,
        payload={"action": "advance", "fromStageId": str(stages[-1])},
    )
    return SimpleNamespace(
        a=a,
        b=b,
        actor=actor,
        card=card,
        visits=visits,
        events=[event],
        versions={version_id: version},
        stages=stages,
    )


def report(h, **overrides):
    data = dict(
        demands=[h.card],
        visits=h.visits,
        events=h.events,
        entries=[],
        versions=h.versions,
        profiles={},
        stages={},
        workflows={},
        companies={},
        categories={},
        scope_profile_id=None,
        started_at=NOW - timedelta(days=30),
        ended_at=NOW,
        now=NOW,
        timezone_name="America/Sao_Paulo",
        warning_days=7,
    )
    return build_analytics(**(data | overrides))


def test_one_credit_per_person_card_with_several_stages_not_button_actor(history):
    result = report(history)
    assert result["summary"]["confirmedDeliveries"] == 2
    assert result["summary"]["completedCards"] == 1
    assert result["summary"]["stageAdvances"] == 3
    people = {row["profileId"]: row for row in result["people"]}
    assert people[str(history.a)]["confirmedDeliveries"] == 1
    assert people[str(history.a)]["stageAdvances"] == 2
    assert people[str(history.b)]["confirmedDeliveries"] == 1
    assert str(history.actor) not in people
    assert result["summary"]["onTimeRate"] == 100
    assert result["stages"][0]["slaRate"] == 100


def test_final_date_confirms_prior_period_stage_and_person_report(history):
    result = report(
        history, scope_profile_id=history.a, started_at=NOW - timedelta(days=2, hours=1)
    )
    assert result["summary"]["stageAdvances"] == 0
    assert result["summary"]["confirmedDeliveries"] == 1
    assert result["summary"]["completedCards"] == 1
    assert [p["profileId"] for p in result["people"]] == [str(history.a)]
    before_final = report(history, ended_at=NOW - timedelta(days=2, hours=1))
    assert before_final["summary"]["confirmedDeliveries"] == 0


def test_reopen_suspends_credit_and_recompletion_still_deduplicates(history):
    history.card.status = "IN_PROGRESS"
    result = report(history)
    assert result["summary"]["confirmedDeliveries"] == 0
    assert result["summary"]["awaitingFinal"] == 2
    assert result["summary"]["completedCards"] == 0
    history.card.status = "COMPLETED"
    old = history.visits[-1]
    history.visits.append(
        DemandStageVisit(
            id=uuid.uuid4(),
            organization_id=old.organization_id,
            demand_id=old.demand_id,
            workflow_version_id=old.workflow_version_id,
            workflow_stage_id=old.workflow_stage_id,
            visit_number=4,
            action="MANUAL",
            entered_at=NOW - timedelta(hours=3),
            left_at=NOW - timedelta(hours=1),
            assignee_id=history.b,
            entered_by=history.actor,
            left_by=history.actor,
            inferred=False,
            acceptance_snapshot={"exitAction": "COMPLETE"},
        )
    )
    history.events.append(
        DemandUpdate(
            id=uuid.uuid4(),
            demand_id=old.demand_id,
            kind="DEMAND_COMPLETED",
            created_at=NOW - timedelta(hours=1),
            created_by=history.actor,
            payload={"action": "advance", "fromStageId": str(old.workflow_stage_id)},
        )
    )
    result = report(history)
    assert result["summary"]["confirmedDeliveries"] == 2
    assert result["summary"]["completedCards"] == 1


def test_imported_inferred_and_manual_status_completion_are_not_final_proof(history):
    history.visits[-1].inferred = True
    history.events[-1].payload = {"status": "COMPLETED"}
    result = report(history)
    assert result["summary"]["completedCards"] == 1
    assert result["summary"]["confirmedDeliveries"] == 0
    assert result["summary"]["awaitingFinal"] == 1  # same person owns the first two stages
    assert result["quality"]["completedWithoutFinalEvidence"] == 1
    assert result["quality"]["inferredVisitsExcluded"] == 1


def test_legacy_exit_uses_next_entry_and_terminal_completion_evidence(history):
    for index, visit in enumerate(history.visits):
        visit.acceptance_snapshot = {
            "fromStageId": str(history.stages[index - 1]) if index else None
        }
        if index:
            visit.entered_at = history.visits[index - 1].left_at
    assert (
        stage_exit(history.visits[0], history.visits[1], history.events, history.versions)
        == "ADVANCE"
    )
    assert stage_exit(history.visits[-1], None, history.events, history.versions) == "COMPLETE"
    result = report(history)
    assert result["summary"]["confirmedDeliveries"] == 2
    assert result["summary"]["onTimeRate"] is None
    assert all(row["slaRate"] is None for row in result["stages"])


@pytest.mark.parametrize("action", ["REASSIGN", "SKIP", "RETURN"])
def test_non_forward_exits_do_not_credit_delivery(history, action):
    history.visits[0].acceptance_snapshot["exitAction"] = action
    history.visits[1].acceptance_snapshot["exitAction"] = action
    result = report(history)
    assert result["summary"]["confirmedDeliveries"] == 1
    assert str(history.a) not in {row["profileId"] for row in result["people"]}


def test_manual_jump_forward_counts_but_return_and_nonterminal_complete_do_not(history):
    visit = history.visits[0]
    visit.acceptance_snapshot = {"exitAction": "MANUAL", "exitStageId": str(history.stages[-1])}
    assert stage_exit(visit, None, history.events, history.versions) == "ADVANCE"
    visit.acceptance_snapshot["exitStageId"] = str(history.stages[0])
    assert stage_exit(visit, None, history.events, history.versions) is None
    visit.acceptance_snapshot = {"exitAction": "COMPLETE"}
    assert stage_exit(visit, None, history.events, history.versions) is None


def test_time_excludes_other_people_open_timers_and_deleted_entries(history):
    def entry(person, state="COMPLETED", deleted=False):
        return TimeEntry(
            id=uuid.uuid4(),
            demand_id=history.card.id,
            user_profile_id=person,
            started_at=NOW - timedelta(hours=2),
            ended_at=NOW - timedelta(hours=1),
            duration_minutes=60,
            state=state,
            deleted_at=NOW if deleted else None,
        )

    result = report(
        history,
        scope_profile_id=history.a,
        entries=[
            entry(history.a),
            entry(history.b),
            entry(history.a, "RUNNING"),
            entry(history.a, deleted=True),
        ],
    )
    assert result["summary"]["trackedMinutes"] == 60
    assert result["timeAllocation"][0]["minutes"] == 60


@pytest.mark.parametrize(
    "delta,expected",
    [
        (-1, "Prazo vencido"),
        (0, "Prazo em menos de 7 dias"),
        (7 * 86400 - 1, "Prazo em menos de 7 dias"),
        (7 * 86400, None),
        (8 * 86400, None),
    ],
)
def test_alert_deadline_boundaries(delta, expected):
    card = Demand(status="IN_PROGRESS", deadline_at=NOW + timedelta(seconds=delta))
    assert alert_reasons(card, PolicyOut(), NOW) == ([expected] if expected else [])


def test_alert_settings_and_terminal_states(history):
    card = history.card
    assert alert_reasons(card, PolicyOut(), NOW) == []
    card.status = "IN_PROGRESS"
    assert "Aprovação pendente" in alert_reasons(card, PolicyOut(), NOW, "Aprovação editorial")
    assert alert_reasons(card, PolicyOut(enabled=False), NOW) == []
    card.archived_at = NOW
    assert alert_reasons(card, PolicyOut(), NOW) == []
    card.archived_at = None
    card.deleted_at = NOW
    assert alert_reasons(card, PolicyOut(), NOW) == []


def test_recorded_exit_of_legacy_inferred_entry_confirms_delivery_without_guessing_duration(
    history,
):
    visit = history.visits[0]
    visit.inferred = True
    visit.acceptance_snapshot["exitRecordedAt"] = visit.left_at.isoformat()
    result = report(history)
    assert result["summary"]["confirmedDeliveries"] == 2
    assert result["summary"]["stageAdvances"] == 3
    assert all(row["id"] != str(visit.workflow_stage_id) for row in result["stages"])
