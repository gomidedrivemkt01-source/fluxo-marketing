"""Integration suite. Only accepts an explicitly named disposable local database."""

import os
import uuid
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api.catalogs import (
    JobRoleInput,
    JobRoleUpdate,
    WorkflowStageInput,
    create_job_role,
    create_workflow_stage,
    list_workflow_stages,
    list_workflows,
    update_job_role,
)
from app.api.demands import (
    apply_stage_snapshot_defaults,
    ensure_demand_stage_instances,
    ensure_workflow_version,
    resolve_stage_assignee,
    validate_stage_handoff,
    version_stage,
)
from app.api.errors import ApiError
from app.api.management import stage_function_groups
from app.auth.service import Principal
from app.models import (
    AuditEvent,
    AuthAccount,
    BriefingTemplate,
    BriefingTemplateVersion,
    CategoryTemplateBinding,
    ChecklistTemplateItem,
    Comment,
    Demand,
    DemandCategory,
    DemandChecklistItem,
    DemandStageInstance,
    DemandTodoItem,
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
from app.stage_functions import (
    StageFunctionBinding,
    bind_stage_function,
    job_role_removal_preview,
    list_stage_function_groups,
    remove_job_role,
)
from app.workflow_blueprints import BLUEPRINTS, apply_blueprint
from app.workflow_simplification import WorkflowSimplification, simplify_workflows

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


def test_simplification_preserves_history_manual_cards_and_todos(setup):
    s = setup
    item = ChecklistTemplateItem(
        organization_id=s.org.id,
        workflow_stage_id=s.stages[0].id,
        title="Conferência antiga",
        position=1,
        required=True,
    )
    s.db.add(item)
    s.db.flush()
    history = DemandChecklistItem(
        demand_id=s.cards[2].id,
        template_item_id=item.id,
        completed=True,
        completed_by=s.people[1][0].id,
    )
    todo = DemandTodoItem(
        organization_id=s.org.id,
        demand_id=s.cards[0].id,
        title="Tarefa manual",
        position=1,
        created_by=s.people[0][0].id,
    )
    s.db.add_all([history, todo])
    s.db.flush()
    frozen = deepcopy(s.version.definition)
    config = WorkflowSimplification.model_validate(
        {
            "functions": [
                {
                    "code": "WRITING",
                    "name": "Redação",
                    "primaryName": "Pessoa 0",
                    "fallbackName": "Pessoa 2",
                }
            ],
            "stages": [
                {"workflowCode": "VIDEO", "stageCode": stage.code, "functionCode": "WRITING"}
                for stage in s.stages
            ],
        }
    )
    result = simplify_workflows(s.db, s.principal, config, apply=True)
    assert result["checklistsDisabled"] == 1
    assert item.active is False
    assert s.db.get(DemandChecklistItem, history.id).completed is True
    assert s.db.get(DemandTodoItem, todo.id).title == "Tarefa manual"
    assert s.version.definition == frozen
    assert s.cards[0].current_assignee_id == s.people[0][0].id
    assert s.cards[1].current_assignee_id == s.people[3][0].id  # explicit card choice
    assert s.cards[2].current_assignee_id == s.people[1][0].id  # completed history
    validate_stage_handoff(s.db, s.cards[0], require_checklist=True)
    role = s.db.scalar(
        select(JobRole).where(JobRole.organization_id == s.org.id, JobRole.code == "WRITING")
    )
    assert all(stage.owner_role_id == role.id for stage in s.stages)
    assert all(stage.default_assignee_id is None for stage in s.stages)
    audit_count = s.db.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.organization_id == s.org.id)
    )
    revisions = [stage.revision for stage in s.stages]
    repeated = simplify_workflows(s.db, s.principal, config, apply=True)
    assert repeated["checklistsDisabled"] == 0
    assert repeated["createdFunctions"] == []
    assert repeated["responsibilities"] == {}
    assert [stage.revision for stage in s.stages] == revisions
    assert (
        s.db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.organization_id == s.org.id)
        )
        == audit_count
    )


def test_simplification_preview_rolls_back_and_is_scoped(setup):
    s = setup
    config = WorkflowSimplification.model_validate(
        {
            "functions": [
                {
                    "code": "WRITING",
                    "name": "Redação",
                    "primaryName": "Pessoa 0",
                    "fallbackName": "Pessoa 2",
                }
            ],
            "stages": [
                {"workflowCode": "VIDEO", "stageCode": "BRIEFING", "functionCode": "WRITING"}
            ],
        }
    )
    savepoint = s.db.begin_nested()
    result = simplify_workflows(s.db, s.principal, config)
    assert result["createdFunctions"] == ["WRITING"]
    assert s.cards[0].current_assignee_id == s.people[1][0].id
    assert s.stages[0].owner_role_id == s.role.id
    savepoint.rollback()
    assert (
        s.db.scalar(
            select(JobRole).where(JobRole.organization_id == s.org.id, JobRole.code == "WRITING")
        )
        is None
    )
    config.functions[0].primary_name = "Pessoa inexistente"
    with pytest.raises(ValueError, match="ausente ou ambíguo"):
        simplify_workflows(s.db, s.principal, config, apply=True)


def test_blueprint_sync_no_longer_generates_stage_checklists(setup):
    s = setup
    for code, spec in BLUEPRINTS.items():
        s.db.add(DemandCategory(organization_id=s.org.id, code=code, name=spec["name"]))
    s.db.flush()
    result = apply_blueprint(s.db, s.principal)
    assert result["checklistsCreated"] == 0
    assert (
        s.db.scalar(
            select(func.count())
            .select_from(ChecklistTemplateItem)
            .where(ChecklistTemplateItem.organization_id == s.org.id)
        )
        == 0
    )


def test_simplification_reuses_existing_function_name_without_changing_its_code(setup):
    s = setup
    config = WorkflowSimplification.model_validate(
        {
            "functions": [
                {
                    "code": "CANONICAL_DESIGN",
                    "name": "Design",
                    "primaryName": "Pessoa 0",
                    "fallbackName": "Pessoa 2",
                }
            ],
            "stages": [
                {
                    "workflowCode": "VIDEO",
                    "stageCode": "BRIEFING",
                    "functionCode": "CANONICAL_DESIGN",
                }
            ],
        }
    )
    result = simplify_workflows(s.db, s.principal, config, apply=True)
    assert result["createdFunctions"] == []
    assert s.role.code == "DESIGN"
    assert s.stages[0].owner_role_id == s.role.id
    assert s.cards[0].current_assignee_id == s.people[0][0].id


@pytest.mark.parametrize("source", ["stdin", "file"])
def test_packaged_workflow_cli_accepts_private_configuration(
    setup, monkeypatch, capsys, tmp_path, source
):
    import json

    from app import workflow_simplification_cli as cli

    s = setup
    config = json.dumps(
        {
            "functions": [
                {
                    "code": "WRITING",
                    "name": "Redação",
                    "primaryName": "Pessoa 0",
                    "fallbackName": "Pessoa 2",
                }
            ],
            "stages": [
                {"workflowCode": "VIDEO", "stageCode": "BRIEFING", "functionCode": "WRITING"}
            ],
        },
        ensure_ascii=False,
    )
    path = tmp_path / "private.json"
    path.write_text(config, encoding="utf-8")
    monkeypatch.setattr(cli.sys, "stdin", StringIO(config))
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "cli",
            "--organization",
            s.org.slug,
            "--actor",
            "Pessoa 0",
            "--config",
            "-" if source == "stdin" else str(path),
            "--apply",
        ],
    )
    monkeypatch.setattr(cli, "Session", lambda _: nullcontext(s.db))
    cli.main()
    output = capsys.readouterr().out
    assert output.isascii()
    result = json.loads(output)
    assert result["applied"] is True
    assert result["createdFunctions"] == ["WRITING"]
    assert s.cards[0].current_assignee_id == s.people[0][0].id


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


def add_shared_role(s, person_index=1):
    role = create_job_role(
        JobRoleInput(code="SHARED", name="Planejamento de Demandas"), s.principal, s.db
    )
    s.db.add(
        MemberRoleAssignment(
            organization_id=s.org.id,
            membership_id=s.people[person_index][1].id,
            job_role_id=role.id,
            priority=10,
        )
    )
    s.db.flush()
    return role


def binding_for(s, key, role):
    group = next(g for g in list_stage_function_groups(s.db, s.org.id) if g["key"] == key)
    return StageFunctionBinding(
        roleId=role.id if role else None,
        stages=[{"id": item["id"], "revision": item["revision"]} for item in group["stages"]],
    )


def test_shared_group_binds_multiple_workflows_without_rewriting_versions(setup):
    s = setup
    from copy import deepcopy

    definition = deepcopy(s.version.definition)
    deadline = s.cards[0].deadline_at
    role = add_shared_role(s, 2)
    result = bind_stage_function(s.db, s.principal, "briefing", binding_for(s, "briefing", role))
    assert result["stages"] == 2
    assert s.stages[0].owner_role_id == role.id
    assert s.default_stages[0].owner_role_id == role.id
    assert s.cards[0].current_assignee_id == s.people[2][0].id
    assert s.cards[1].current_assignee_id == s.people[3][0].id
    assert s.cards[2].current_assignee_id == s.people[1][0].id
    assert s.cards[0].deadline_at == deadline
    assert s.version.definition == definition


def test_same_owner_binding_persists_for_future_role_changes_and_handoffs(setup):
    s = setup
    role = add_shared_role(s, 1)
    bind_stage_function(s.db, s.principal, "producao", binding_for(s, "producao", role))
    future = s.db.scalar(
        select(DemandStageInstance).where(
            DemandStageInstance.demand_id == s.cards[0].id,
            DemandStageInstance.workflow_stage_id == s.stages[1].id,
        )
    )
    assert future.assignment_defaults["ownerRoleId"] == str(role.id)
    # A versão congelada ainda aponta à função antiga. A atribuição operacional acompanha a nova.
    assert version_stage(s.version, s.stages[1].id)["ownerRoleId"] == str(s.role.id)
    apply_responsibilities(
        s.db,
        s.principal,
        ResponsibilityChange(
            roles=[
                {
                    "roleId": role.id,
                    "primaryProfileId": s.people[2][0].id,
                    "fallbackProfileId": None,
                    "expectedRevision": role.revision,
                }
            ],
            applyToCurrent=True,
        ),
    )
    assert future.assignee_id == s.people[2][0].id
    s.cards[0].current_stage_id = s.stages[1].id
    apply_stage_snapshot_defaults(s.cards[0], version_stage(s.version, s.stages[1].id), db=s.db)
    assert s.cards[0].current_assignee_id == s.people[2][0].id


def test_group_binding_rejects_stale_and_foreign_stage_membership(setup):
    s = setup
    payload = binding_for(s, "briefing", s.role)
    payload.stages.pop()
    with pytest.raises(ApiError) as caught:
        bind_stage_function(s.db, s.principal, "briefing", payload)
    assert caught.value.status_code == 409
    assert s.cards[0].current_assignee_id == s.people[1][0].id


def test_removing_role_unlinks_defaults_and_preserves_manual_and_completed_history(setup):
    s = setup
    old_id, old_name, old_code = s.role.id, s.role.name, s.role.code
    preview = job_role_removal_preview(s.db, s.principal, old_id)
    assert preview["stages"] == 6
    remove_job_role(s.db, s.principal, old_id, s.role.revision)
    assert not s.role.active
    assert all(stage.owner_role_id is None for stage in [*s.stages, *s.default_stages])
    assert s.cards[0].current_assignee_id is None
    assert s.cards[1].current_assignee_id == s.people[3][0].id
    assert s.cards[2].current_assignee_id == s.people[1][0].id
    assert s.db.get(Comment, s.comment.id).author_id == s.people[1][0].id
    assert version_stage(s.version, s.stages[0].id)["ownerRoleId"] == str(old_id)
    recreated = create_job_role(JobRoleInput(name=old_name, code=old_code), s.principal, s.db)
    assert recreated.id != old_id
    assert resolve_stage_assignee(s.db, s.cards[0], owner_role_id=old_id) is None


def test_role_removal_uses_direct_stage_fallback_and_checks_revision(setup):
    s = setup
    s.stages[0].fallback_user_id = s.people[2][0].id
    s.db.flush()
    with pytest.raises(ApiError) as caught:
        remove_job_role(s.db, s.principal, s.role.id, s.role.revision + 1)
    assert caught.value.status_code == 409
    remove_job_role(s.db, s.principal, s.role.id, s.role.revision)
    assert s.cards[0].current_assignee_id == s.people[2][0].id
    assert s.stages[0].fallback_user_id == s.people[2][0].id


def test_role_edit_and_group_access_require_organization_permissions(setup):
    s = setup
    updated = update_job_role(
        s.role.id,
        JobRoleUpdate(code=s.role.code, name="Copywriter", expectedRevision=s.role.revision),
        s.principal,
        s.db,
    )
    assert updated.id == s.role.id and updated.name == "Copywriter"
    s.principal.role.permissions = ["catalog:read"]
    with pytest.raises(ApiError) as caught:
        stage_function_groups(s.principal, s.db)
    assert caught.value.status_code == 403


def test_new_stage_inherits_shared_role_but_allows_explicit_no_function(setup):
    s = setup
    workflow = Workflow(organization_id=s.org.id, code="NOVO", name="Novo fluxo")
    s.db.add(workflow)
    s.db.flush()
    role = add_shared_role(s)
    bind_stage_function(s.db, s.principal, "briefing", binding_for(s, "briefing", role))
    created = create_workflow_stage(
        WorkflowStageInput(name="Briefing", code="BRIEFING", position=1, workflowId=workflow.id),
        s.principal,
        s.db,
    )
    assert created.owner_role_id == role.id
    independent = create_workflow_stage(
        WorkflowStageInput(
            name="Briefing",
            code="BRIEFING_EXTRA",
            position=2,
            workflowId=workflow.id,
            ownerRoleId=None,
        ),
        s.principal,
        s.db,
    )
    assert independent.owner_role_id is None


def test_function_removal_refuses_running_timer_without_partial_unlink(setup):
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
    with pytest.raises(ApiError) as caught:
        remove_job_role(s.db, s.principal, s.role.id, s.role.revision)
    assert caught.value.code == "running_timers"
    assert s.role.active and s.stages[0].owner_role_id == s.role.id


def test_function_binding_and_removal_cannot_cross_organizations(setup):
    s = setup
    other = Organization(name="Outra", slug=f"other-{uuid.uuid4()}")
    s.db.add(other)
    s.db.flush()
    foreign = JobRole(organization_id=other.id, name="Restrita", code="RESTRITA")
    s.db.add(foreign)
    s.db.flush()
    with pytest.raises(ApiError) as caught:
        bind_stage_function(s.db, s.principal, "briefing", binding_for(s, "briefing", foreign))
    assert caught.value.code == "role_invalid"
    with pytest.raises(ApiError) as caught:
        remove_job_role(s.db, s.principal, foreign.id, foreign.revision)
    assert caught.value.status_code == 404


def test_automatic_function_inheritance_refuses_ambiguous_groups(setup):
    s = setup
    s.stages[0].owner_role_id = None
    s.db.flush()
    with pytest.raises(ApiError) as caught:
        create_workflow_stage(
            WorkflowStageInput(name="Briefing", code="EXTRA", position=4, workflowId=s.source.id),
            s.principal,
            s.db,
        )
    assert caught.value.code == "stage_function_ambiguous"
