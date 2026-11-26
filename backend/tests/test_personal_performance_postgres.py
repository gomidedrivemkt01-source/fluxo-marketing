import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from test_management_postgres import setup as setup  # noqa: F401

from app.api.demands import ensure_workflow_version
from app.api.errors import ApiError
from app.api.performance import personal_performance
from app.auth.service import Principal
from app.models import (
    Demand,
    DemandStageVisit,
    Organization,
    PermissionRole,
    TimeEntry,
    Workflow,
    WorkflowStage,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("FM_MANAGEMENT_TEST_DSN"), reason="Local disposable PostgreSQL required"
)


def read(s, **overrides):
    args = dict(
        start_date=None,
        end_date=None,
        gap_minutes=90,
        day_start="08:00",
        day_end="18:00",
        principal=s.principal,
        db=s.db,
    )
    return personal_performance(**(args | overrides))


def test_own_scope_excludes_other_people_and_other_organizations(setup):
    s = setup
    now = datetime.now(UTC)
    own = s.people[0][0].id
    other = Organization(name="Outra equipe sintética", slug="other-" + s.org.id.hex)
    s.db.add(other)
    s.db.flush()
    foreign_workflow = Workflow(
        organization_id=other.id, name="Outro fluxo", code="OTHER", is_default=True
    )
    s.db.add(foreign_workflow)
    s.db.flush()
    foreign_stage = WorkflowStage(
        organization_id=other.id,
        workflow_id=foreign_workflow.id,
        name="Produção",
        code="CREATE",
        position=1,
        color="#123456",
    )
    s.db.add(foreign_stage)
    s.db.flush()
    foreign_version = ensure_workflow_version(s.db, other.id, foreign_workflow.id, own)
    foreign = Demand(
        organization_id=other.id,
        public_id="OTHER-" + s.org.id.hex[:20],
        title="Dado de outra organização",
        workflow_id=foreign_workflow.id,
        workflow_version_id=foreign_version.id,
        current_stage_id=foreign_stage.id,
        created_by=own,
        current_assignee_id=own,
        status="IN_PROGRESS",
    )
    s.db.add(foreign)
    s.db.flush()
    for organization, card, person, minutes in [
        (s.org.id, s.cards[0], own, 30),
        (s.org.id, s.cards[0], s.people[1][0].id, 300),
        (other.id, foreign, own, 900),
    ]:
        s.db.add(
            TimeEntry(
                organization_id=organization,
                demand_id=card.id,
                user_profile_id=person,
                source="MANUAL",
                state="COMPLETED",
                started_at=now - timedelta(minutes=40),
                ended_at=now - timedelta(minutes=10),
                duration_minutes=minutes,
            )
        )
    s.db.flush()
    collaborator = Principal(
        s.principal.session,
        s.people[0][0],
        s.people[0][1],
        PermissionRole(code="collaborator", permissions=["demands:read"]),
    )
    r = read(
        s,
        principal=collaborator,
        start_date=now.astimezone(ZoneInfo("America/Sao_Paulo")).date() - timedelta(days=1),
        end_date=now.astimezone(ZoneInfo("America/Sao_Paulo")).date(),
    )
    assert r["profileId"] == str(own)
    assert r["summary"]["recordedMinutes"] == 30
    assert all(segment["title"] != "Dado de outra organização" for segment in r["segments"])
    assert {segment["id"] for segment in r["segments"]} == {str(s.cards[0].id)}


def test_previous_stage_contributor_keeps_their_delivery_after_reassignment(setup):
    s = setup
    now = datetime.now(UTC)
    s.db.add(
        DemandStageVisit(
            organization_id=s.org.id,
            demand_id=s.cards[0].id,
            workflow_version_id=s.version.id,
            workflow_stage_id=s.stages[0].id,
            visit_number=1,
            action="START",
            assignee_id=s.people[0][0].id,
            entered_by=s.people[1][0].id,
            left_by=s.people[1][0].id,
            entered_at=now - timedelta(hours=2),
            left_at=now - timedelta(minutes=10),
            acceptance_snapshot={
                "exitAction": "ADVANCE",
                "exitRecordedAt": (now - timedelta(minutes=10)).isoformat(),
            },
        )
    )
    s.db.flush()
    r = read(
        s,
        start_date=now.astimezone(ZoneInfo("America/Sao_Paulo")).date() - timedelta(days=1),
        end_date=now.astimezone(ZoneInfo("America/Sao_Paulo")).date(),
    )
    assert r["summary"]["stageAdvances"] == 1 and r["summary"]["deliveredCards"] == 1
    assert r["deliveries"][0]["id"] == str(s.cards[0].id)


@pytest.mark.parametrize("start_delta,end_delta", [(0, 1), (-32, 0), (0, -1)])
def test_invalid_or_future_period_is_rejected(setup, start_delta, end_delta):
    s = setup
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    with pytest.raises(ApiError) as invalid:
        read(
            s,
            start_date=today + timedelta(days=start_delta),
            end_date=today + timedelta(days=end_delta),
        )
    assert invalid.value.status_code == 422


def test_period_and_tracking_window_are_validated(setup):
    s = setup
    with pytest.raises(ApiError):
        read(s, start_date=datetime.now(UTC).date(), end_date=None)
    with pytest.raises(ApiError):
        read(s, day_start="18:00", day_end="08:00")
