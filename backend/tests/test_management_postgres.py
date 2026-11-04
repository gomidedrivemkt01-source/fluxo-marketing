"""Integration suite. Only accepts an explicitly named disposable local database."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api.catalogs import list_workflow_stages, list_workflows
from app.api.demands import (
    ensure_demand_stage_instances,
    ensure_workflow_version,
    resolve_stage_assignee,
)
from app.api.errors import ApiError
from app.auth.service import Principal
from app.models import (
    AuditEvent,
    AuthAccount,
    BriefingTemplate,
    BriefingTemplateVersion,
    CategoryTemplateBinding,
    Comment,
    Demand,
    DemandCategory,
    DemandStageInstance,
    JobRole,
    MemberRoleAssignment,
    Membership,
    MembershipStatus,
    Organization,
    PermissionRole,
    TimeEntry,
    UserProfile,
    Workflow,
    WorkflowStage,
    WorkflowVersion,
)
from app.operational_management import (
    ResponsibilityChange,
    apply_responsibilities,
    removal_preview,
    remove_person,
    remove_workflow_or_stage,
    responsibility_plan,
)

DSN = os.environ.get("FM_MANAGEMENT_TEST_DSN", "")
pytestmark = pytest.mark.skipif(
    not DSN, reason="Set FM_MANAGEMENT_TEST_DSN for isolated PostgreSQL integration tests"
)


@pytest.fixture
def setup():
    url = make_url(DSN)
    assert url.host in {"127.0.0.1", "localhost"} and url.database == "fm_test_management"
    engine = create_engine(DSN)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    org = Organization(name="Equipe sintética", slug=f"test-{uuid.uuid4()}")
    db.add(org)
    db.flush()
    access = PermissionRole(
        organization_id=org.id, code="admin", name="Administrador", permissions=["*"]
    )
    db.add(access)
    db.flush()
    people = []
    for number in range(4):
        account = AuthAccount(
            id=uuid.uuid4(), email=f"p{number}-{org.id}@example.com", password_hash="test-only"
        )
        profile = UserProfile(
            auth_user_id=account.id, email=account.email, full_name=f"Pessoa {number}"
        )
        db.add_all([account, profile])
        db.flush()
        member = Membership(
            organization_id=org.id,
            user_profile_id=profile.id,
            permission_role_id=access.id,
            status=MembershipStatus.ACTIVE,
        )
        db.add(member)
        db.flush()
        people.append((profile, member))
    principal = Principal(MagicMock(), people[0][0], people[0][1], access)
    role = JobRole(organization_id=org.id, code="DESIGN", name="Design")
    default = Workflow(organization_id=org.id, code="DEFAULT", name="Padrão", is_default=True)
    source = Workflow(organization_id=org.id, code="VIDEO", name="Vídeo", is_default=False)
    db.add_all([role, default, source])
    db.flush()
    for number, fallback in ((1, False), (2, True)):
        db.add(
            MemberRoleAssignment(
                organization_id=org.id,
                membership_id=people[number][1].id,
                job_role_id=role.id,
                is_fallback=fallback,
                priority=20 if fallback else 10,
            )
        )
    stages = []
    default_stages = []
    for workflow, destination in ((source, stages), (default, default_stages)):
        for position, code in enumerate(("BRIEFING", "PRODUCAO", "ENTREGA"), 1):
            stage = WorkflowStage(
                organization_id=org.id,
                workflow_id=workflow.id,
                name=code,
                code=code,
                position=position,
                color="#123456",
                owner_role_id=role.id,
                expected_duration_hours=12,
            )
            db.add(stage)
            db.flush()
            destination.append(stage)
    category = DemandCategory(
        organization_id=org.id, code="VIDEO", name="Vídeo", default_workflow_id=source.id
    )
    db.add(category)
    db.flush()
    version = ensure_workflow_version(db, org.id, source.id, people[0][0].id)
    cards = []
    for number in range(3):
        card = Demand(
            organization_id=org.id,
            public_id=f"TEST-{org.id.hex[:12]}-{number}",
            title=f"Card {number}",
            workflow_id=source.id,
            workflow_version_id=version.id,
            current_stage_id=stages[0].id,
            current_assignee_id=people[3 if number == 1 else 1][0].id,
            created_by=people[0][0].id,
            status="COMPLETED" if number == 2 else "IN_PROGRESS",
            source="test",
            priority="NORMAL",
            category_id=category.id,
            deadline_at=datetime.now(UTC) - timedelta(days=3),
        )
        db.add(card)
        db.flush()
        ensure_demand_stage_instances(db, card, version)
        cards.append(card)
    comment = Comment(
        demand_id=cards[0].id, author_id=people[1][0].id, content="Comentário histórico"
    )
    db.add(comment)
    db.flush()
    yield SimpleNamespace(
        db=db,
        org=org,
        people=people,
        principal=principal,
        role=role,
        source=source,
        default=default,
        stages=stages,
        default_stages=default_stages,
        category=category,
        version=version,
        cards=cards,
        comment=comment,
    )
    db.close()
    transaction.rollback()
    connection.close()
    engine.dispose()


def role_change(s):
    return ResponsibilityChange(
        roles=[
            {
                "roleId": s.role.id,
                "primaryProfileId": s.people[2][0].id,
                "fallbackProfileId": s.people[1][0].id,
                "expectedRevision": s.role.revision,
            }
        ],
        applyToCurrent=True,
    )


def test_bulk_role_change_preserves_manual_owner_deadlines_and_completed_cards(setup):
    s = setup
    deadline = s.cards[0].deadline_at
    preview = responsibility_plan(s.db, s.principal, role_change(s))[0]
    assert preview["currentDemands"] == 1
    assert preview["futureStages"] == 4
    apply_responsibilities(s.db, s.principal, role_change(s))
    assert s.cards[0].current_assignee_id == s.people[2][0].id
    assert s.cards[0].deadline_at == deadline
    assert s.cards[1].current_assignee_id == s.people[3][0].id
    assert s.cards[2].current_assignee_id == s.people[1][0].id
    assert s.db.get(Comment, s.comment.id).author_id == s.people[1][0].id
    assert (
        s.db.scalar(
            select(AuditEvent).where(
                AuditEvent.organization_id == s.org.id,
                AuditEvent.event_type == "RESPONSIBILITIES_UPDATED",
            )
        )
        is not None
    )


def test_bulk_update_handles_cards_without_materialized_stage_plan(setup):
    s = setup
    from sqlalchemy import delete

    s.db.execute(delete(DemandStageInstance).where(DemandStageInstance.demand_id == s.cards[0].id))
    apply_responsibilities(s.db, s.principal, role_change(s))
    future = list(
        s.db.scalars(
            select(DemandStageInstance).where(
                DemandStageInstance.demand_id == s.cards[0].id,
                DemandStageInstance.state == "upcoming",
            )
        )
    )
    assert len(future) == 2
    assert all(i.assignee_id == s.people[2][0].id for i in future)


def test_bulk_update_blocks_running_timer_before_mutating_roles(setup):
    s = setup
    s.db.add(
        TimeEntry(
            organization_id=s.org.id,
            demand_id=s.cards[0].id,
            user_profile_id=s.people[1][0].id,
            source="TIMER",
            state="RUNNING",
            started_at=datetime.now(UTC),
        )
    )
    s.db.flush()
    with pytest.raises(ApiError) as error:
        apply_responsibilities(s.db, s.principal, role_change(s))
    assert error.value.code == "running_timers"
    assert s.role.revision == 1
    assert s.cards[0].current_assignee_id == s.people[1][0].id


def test_stage_removal_rebuilds_plans_and_retains_old_versions(setup):
    s = setup
    old_version_id = s.version.id
    remove_workflow_or_stage(
        s.db,
        s.principal,
        s.source.id,
        s.stages[0].revision,
        stage_id=s.stages[0].id,
        target_stage_id=s.stages[1].id,
    )
    assert s.cards[0].current_stage_id == s.stages[1].id
    assert s.cards[0].workflow_version_id != old_version_id
    assert s.db.get(WorkflowVersion, old_version_id) is not None
    assert s.db.get(WorkflowStage, s.stages[0].id).removed_at is not None
    listed = list_workflow_stages(True, True, s.source.id, True, s.principal, s.db)
    assert s.stages[0].id not in {stage.id for stage in listed}


def test_workflow_removal_transfers_categories_cards_and_keeps_comments(setup):
    s = setup
    preview = removal_preview(s.db, s.principal, s.source.id)
    assert preview["categories"] == 1 and preview["migratedDemands"] == 3
    remove_workflow_or_stage(s.db, s.principal, s.source.id, s.source.revision)
    assert all(card.workflow_id == s.default.id for card in s.cards)
    assert all(card.current_stage_id == s.default_stages[0].id for card in s.cards)
    assert s.category.default_workflow_id == s.default.id
    assert s.db.get(Comment, s.comment.id).content == "Comentário histórico"
    assert s.db.get(Workflow, s.source.id).lifecycle_state == "RETIRED"
    assert s.source.id not in {w.id for w in list_workflows(True, True, s.principal, s.db)}
    assert not any(
        stage.workflow_id == s.source.id
        for stage in list_workflow_stages(True, True, None, True, s.principal, s.db)
    )


def test_person_removal_revokes_authentication_but_preserves_authorship(setup):
    s = setup
    profile, member = s.people[1]
    auth_id = profile.auth_user_id
    member.status = MembershipStatus.SUSPENDED
    s.db.add(
        TimeEntry(
            organization_id=s.org.id,
            demand_id=s.cards[0].id,
            user_profile_id=profile.id,
            source="TIMER",
            state="RUNNING",
            started_at=datetime.now(UTC) - timedelta(minutes=9),
        )
    )
    s.db.flush()
    result = remove_person(s.db, s.principal, member.id, member.revision)
    assert result["historyPreserved"] is True
    assert s.db.get(AuthAccount, auth_id) is None
    assert s.db.get(UserProfile, profile.id).full_name == "Pessoa 1"
    assert s.db.get(Comment, s.comment.id).author_id == profile.id
    assert s.cards[0].current_assignee_id == s.people[2][0].id
    assert s.cards[2].current_assignee_id == profile.id
    timer = s.db.scalar(select(TimeEntry).where(TimeEntry.user_profile_id == profile.id))
    assert timer.state == "COMPLETED" and timer.duration_minutes >= 9


def test_stage_specific_assignment_updates_existing_cards(setup):
    s = setup
    payload = ResponsibilityChange(
        stages=[
            {
                "stageId": s.stages[0].id,
                "ownerRoleId": None,
                "primaryProfileId": s.people[2][0].id,
                "fallbackProfileId": s.people[1][0].id,
                "expectedRevision": s.stages[0].revision,
            }
        ],
        applyToCurrent=True,
    )
    apply_responsibilities(s.db, s.principal, payload)
    assert s.stages[0].default_assignee_id == s.people[2][0].id
    assert s.cards[0].current_assignee_id == s.people[2][0].id
    assert s.cards[1].current_assignee_id == s.people[3][0].id


def test_inactive_direct_assignee_in_frozen_version_is_not_reassigned(setup):
    s = setup
    s.people[1][1].status = MembershipStatus.SUSPENDED
    s.db.flush()
    result = resolve_stage_assignee(
        s.db, s.cards[0], default_assignee_id=s.people[1][0].id, fallback_user_id=s.people[2][0].id
    )
    assert result == s.people[2][0].id


@pytest.mark.parametrize("remove_stage", [False, True])
def test_removal_preserves_briefing_and_replaces_active_category_binding(setup, remove_stage):
    s = setup
    template = BriefingTemplate(
        organization_id=s.org.id, category_id=s.category.id, name="Briefing de vídeo", code="VIDEO"
    )
    s.db.add(template)
    s.db.flush()
    briefing = BriefingTemplateVersion(
        organization_id=s.org.id,
        template_id=template.id,
        version=1,
        state="PUBLISHED",
        definition={"fields": []},
        created_by=s.principal.profile.id,
    )
    s.db.add(briefing)
    s.db.flush()
    old = CategoryTemplateBinding(
        organization_id=s.org.id,
        category_id=s.category.id,
        workflow_version_id=s.version.id,
        briefing_template_version_id=briefing.id,
        effective_from=datetime.now(UTC),
        activated_by=s.principal.profile.id,
    )
    s.db.add(old)
    s.db.flush()
    if remove_stage:
        remove_workflow_or_stage(
            s.db,
            s.principal,
            s.source.id,
            s.stages[0].revision,
            stage_id=s.stages[0].id,
            target_stage_id=s.stages[1].id,
        )
    else:
        remove_workflow_or_stage(s.db, s.principal, s.source.id, s.source.revision)
    current = s.db.scalar(
        select(CategoryTemplateBinding).where(
            CategoryTemplateBinding.category_id == s.category.id,
            CategoryTemplateBinding.effective_until.is_(None),
        )
    )
    assert current.id != old.id
    assert current.briefing_template_version_id == briefing.id
    assert current.workflow_version_id == s.cards[0].workflow_version_id
    assert old.effective_until is not None
