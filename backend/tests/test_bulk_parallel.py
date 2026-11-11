import json
import os
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from test_management_postgres import setup as setup

from app.api.bulk_demands import (
    BulkDocument,
    BulkRequest,
    apply,
    document_hash,
    model_file,
    preview,
)
from app.api.demands import (
    DemandEdit,
    DemandWorkflowAction,
    apply_workflow_action,
    update_demand,
    validate_stage_handoff,
)
from app.api.errors import ApiError
from app.api.time_tracking import (
    TimerStart,
    TimerStop,
    get_active_timers,
    pause_timer,
    start_timer,
    stop_timer,
)
from app.api.work_content import DemandBriefingInput, update_demand_briefing
from app.models import (
    BriefingField,
    BulkDemandItem,
    ChecklistTemplateItem,
    Comment,
    Demand,
    DemandStageInstance,
    DemandUpdate,
    TimeEntry,
)

requires_postgres = pytest.mark.skipif(
    not os.environ.get("FM_MANAGEMENT_TEST_DSN"),
    reason="Banco PostgreSQL descartável não configurado",
)


def document(**changes):
    return {
        "schemaVersion": "fluxo.demands.v1",
        "batchId": "editorial-nov-v1",
        "cards": [
            {
                "externalId": "marca-nov-post-1",
                "title": "Post de lançamento",
                "categoryCode": "VIDEO",
                "assigneeEmail": None,
                "priority": "HIGH",
                "deadlineAt": "2026-11-20T17:00:00-03:00",
                "checklist": ["Conferir texto"],
            },
            {
                "externalId": "marca-nov-post-2",
                "title": "Post seguinte",
                "categoryCode": "VIDEO",
                "deadlineAt": None,
            },
        ],
        **changes,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"schemaVersion": "unknown"},
        {"cards": [{"externalId": "a", "title": "Texto", "deadlineAt": "2026-11-20T17:00:00"}]},
        {"cards": [{"externalId": "a", "title": "Texto", "unknown": True}]},
        {"cards": [{"externalId": "a", "title": "Texto"}] * 2},
        {"cards": [{"externalId": str(i), "title": "Texto"} for i in range(201)]},
    ],
)
def test_document_rejects_unsafe_or_ambiguous_shapes(change):
    with pytest.raises(ValidationError):
        BulkDocument.model_validate(document(**change))


def test_assignee_null_and_omitted_have_different_fingerprints():
    first = document()
    other = document()
    del other["cards"][0]["assigneeEmail"]
    assert document_hash(BulkDocument.model_validate(first)) != document_hash(
        BulkDocument.model_validate(other)
    )


@requires_postgres
def test_return_without_reason_requires_ack_and_keeps_a_chat_record(setup):
    s = setup
    publish(s)
    card = s.cards[0]
    card.current_stage_id = s.stages[1].id
    for item in s.db.scalars(
        select(DemandStageInstance).where(DemandStageInstance.demand_id == card.id)
    ):
        item.state = "current" if item.workflow_stage_id == card.current_stage_id else "upcoming"
    s.db.flush()
    payload = DemandWorkflowAction(
        action="return", targetStageId=s.stages[0].id, expectedRevision=card.revision
    )
    with pytest.raises(ApiError) as caught:
        apply_workflow_action(card.id, payload, s.principal, s.db)
    assert caught.value.code == "acknowledgement_required"
    payload.acknowledged_warnings = ["return_reason_missing"]
    result = apply_workflow_action(card.id, payload, s.principal, s.db)
    assert result.stage_id == s.stages[0].id
    comments = s.db.scalars(select(Comment).where(Comment.demand_id == card.id)).all()
    assert any("ciência registrada" in item.content for item in comments)


def publish(s):
    s.default.lifecycle_state = "PUBLISHED"
    s.source.lifecycle_state = "PUBLISHED"
    s.db.flush()


@requires_postgres
def test_bulk_review_apply_replay_and_cross_batch_deduplication(setup):
    s = setup
    publish(s)
    payload = BulkRequest(document=document())
    before = s.db.scalar(select(func.count()).select_from(Demand))
    review = preview(payload, s.principal, s.db)
    assert review["ready"] == 2 and review["invalid"] == 0
    assert s.db.scalar(select(func.count()).select_from(Demand)) == before
    assert review["rows"][0]["assignee"] == "Sem responsável"
    assert review["rows"][1]["assignee"] == "Pessoa 1"
    payload.previewHash = review["previewHash"]
    result = apply(payload, s.principal, s.db)
    assert result["created"] == 2
    cards = s.db.scalars(
        select(Demand).where(Demand.source == "bulk_json", Demand.organization_id == s.org.id)
    ).all()
    assert cards[0].priority == "HIGH" and cards[0].current_assignee_id is None
    assert cards[1].current_assignee_id == s.people[1][0].id
    assert cards[0].deadline_at == datetime(2026, 11, 20, 20, tzinfo=UTC)
    assert cards[1].deadline_at is None
    assert apply(payload, s.principal, s.db)["alreadyApplied"] is True
    assert s.db.scalar(select(func.count()).select_from(Demand)) == before + 2
    other = BulkRequest(document=document(batchId="editorial-v2"))
    review = preview(other, s.principal, s.db)
    assert review["duplicates"] == 2 and review["ready"] == 0
    other.previewHash = review["previewHash"]
    assert apply(other, s.principal, s.db)["created"] == 0
    assert (
        s.db.scalar(
            select(func.count())
            .select_from(BulkDemandItem)
            .where(BulkDemandItem.organization_id == s.org.id)
        )
        == 2
    )


@requires_postgres
def test_bulk_invalid_row_does_not_create_any_cards(setup):
    s = setup
    publish(s)
    data = document()
    data["cards"][1]["companyCode"] = "FOREIGN_COMPANY"
    payload = BulkRequest(document=data)
    review = preview(payload, s.principal, s.db)
    assert review["invalid"] == 1 and review["rows"][1]["errors"][0]["field"] == "companyCode"
    payload.previewHash = review["previewHash"]
    with pytest.raises(ApiError):
        apply(payload, s.principal, s.db)
    assert not s.db.scalar(
        select(Demand.id).where(Demand.source == "bulk_json", Demand.organization_id == s.org.id)
    )


@requires_postgres
def test_bulk_requires_current_review_and_stable_batch_content(setup):
    s = setup
    publish(s)
    payload = BulkRequest(document=document())
    with pytest.raises(ApiError) as caught:
        apply(payload, s.principal, s.db)
    assert caught.value.code == "bulk_preview_changed"
    payload.previewHash = preview(payload, s.principal, s.db)["previewHash"]
    s.stages[0].revision += 1
    s.db.flush()
    with pytest.raises(ApiError) as caught:
        apply(payload, s.principal, s.db)
    assert caught.value.code == "bulk_preview_changed"
    payload.previewHash = preview(payload, s.principal, s.db)["previewHash"]
    apply(payload, s.principal, s.db)
    changed = document()
    changed["cards"][0]["title"] = "Outro conteúdo"
    with pytest.raises(ApiError) as caught:
        apply(BulkRequest(document=changed), s.principal, s.db)
    assert caught.value.code == "batch_content_changed"


@requires_postgres
def test_model_is_compatible_and_collaborator_can_import(setup):
    s = setup
    publish(s)
    s.principal.role.permissions = ["demands:read", "demands:work"]
    model = BulkDocument.model_validate(json.loads(model_file(s.principal, s.db).body))
    assert model.guide["companies"] == []
    payload = BulkRequest(document=model)
    review = preview(payload, s.principal, s.db)
    payload.previewHash = review["previewHash"]
    assert apply(payload, s.principal, s.db)["created"] == 1
    s.principal.role.permissions = ["demands:read"]
    with pytest.raises(ApiError) as caught:
        preview(payload, s.principal, s.db)
    assert caught.value.status_code == 403


@requires_postgres
def test_two_timers_pause_resume_and_stop_are_independent(setup):
    s = setup
    first = start_timer(s.cards[0].id, TimerStart(), s.principal, s.db)
    second = start_timer(s.cards[1].id, TimerStart(), s.principal, s.db)
    assert len(get_active_timers(s.principal, s.db)) == 2
    with pytest.raises(ApiError) as caught:
        start_timer(s.cards[2].id, TimerStart(), s.principal, s.db)
    assert caught.value.code == "timer_limit_reached"
    assert start_timer(s.cards[0].id, TimerStart(), s.principal, s.db).id == first.id
    pause_timer(s.cards[0].id, TimerStop(expectedRevision=first.revision), s.principal, s.db)
    resumed = start_timer(s.cards[0].id, TimerStart(), s.principal, s.db)
    assert resumed.state == "RUNNING" and resumed.id == first.id
    stop_timer(s.cards[0].id, TimerStop(expectedRevision=resumed.revision), s.principal, s.db)
    remaining = get_active_timers(s.principal, s.db)
    assert len(remaining) == 1 and remaining[0].timer.id == second.id
    assert start_timer(s.cards[2].id, TimerStart(), s.principal, s.db).state == "RUNNING"


@requires_postgres
def test_database_blocks_duplicate_slot_or_same_card_timers(setup):
    s = setup
    start_timer(s.cards[0].id, TimerStart(), s.principal, s.db)
    with pytest.raises(IntegrityError), s.db.begin_nested():
        s.db.add(
            TimeEntry(
                organization_id=s.org.id,
                demand_id=s.cards[1].id,
                user_profile_id=s.principal.profile.id,
                source="TIMER",
                state="RUNNING",
                started_at=datetime.now(UTC),
                timer_slot=1,
            )
        )
        s.db.flush()
    with pytest.raises(IntegrityError), s.db.begin_nested():
        s.db.add(
            TimeEntry(
                organization_id=s.org.id,
                demand_id=s.cards[0].id,
                user_profile_id=s.principal.profile.id,
                source="TIMER",
                state="RUNNING",
                started_at=datetime.now(UTC),
                timer_slot=2,
            )
        )
        s.db.flush()


@requires_postgres
def test_past_deadline_requires_explicit_ack_and_records_history(setup):
    s = setup
    publish(s)
    card = s.cards[0]
    original = card.deadline_at
    card.description = "x" * 6000
    s.db.flush()
    payload = DemandEdit(
        title=card.title,
        description=card.description,
        companyId=None,
        categoryId=card.category_id,
        workflowId=card.workflow_id,
        stageId=card.current_stage_id,
        assigneeId=card.current_assignee_id,
        priority=card.priority,
        status=card.status,
        deadlineAt=datetime.now(UTC) - timedelta(days=5),
        expectedRevision=card.revision,
    )
    with pytest.raises(ApiError) as caught:
        update_demand(card.id, payload, s.principal, s.db)
    assert caught.value.code == "acknowledgement_required"
    assert caught.value.details["fieldErrors"][0]["field"] == "deadlineAt"
    assert card.deadline_at == original
    payload.acknowledged_warnings = ["deadline_past"]
    update_demand(card.id, payload, s.principal, s.db)
    event = s.db.scalar(
        select(DemandUpdate).where(
            DemandUpdate.demand_id == card.id, DemandUpdate.kind == "WARNING_ACKNOWLEDGED"
        )
    )
    assert (
        event
        and event.created_by == s.principal.profile.id
        and event.payload["action"] == "edit_demand"
    )
    assert card.description == "x" * 6000


@requires_postgres
def test_briefing_and_checklist_can_proceed_with_audited_ack(setup):
    s = setup
    publish(s)
    field = BriefingField(
        organization_id=s.org.id,
        category_id=s.category.id,
        label="Objetivo",
        key="objetivo",
        field_type="text",
        required=True,
        position=1,
    )
    check = ChecklistTemplateItem(
        organization_id=s.org.id,
        workflow_stage_id=s.stages[0].id,
        title="Revisar texto",
        position=1,
        required=True,
    )
    s.db.add_all([field, check])
    s.db.flush()
    card = s.cards[0]
    payload = DemandBriefingInput(expectedRevision=card.revision, answers=[])
    with pytest.raises(ApiError) as caught:
        update_demand_briefing(card.id, payload, s.principal, s.db)
    assert caught.value.details["warnings"][0]["field"] == str(field.id)
    payload.acknowledged_warnings = [f"briefing:{field.id}"]
    update_demand_briefing(card.id, payload, s.principal, s.db)
    with pytest.raises(ApiError) as caught:
        validate_stage_handoff(s.db, card, require_checklist=True, principal=s.principal)
    assert "Revisar texto" in caught.value.details["warnings"][0]["message"]
    validate_stage_handoff(
        s.db,
        card,
        require_checklist=True,
        principal=s.principal,
        acknowledged=[f"checklist:{check.id}"],
    )
    s.db.flush()
    assert (
        len(
            s.db.scalars(
                select(DemandUpdate).where(
                    DemandUpdate.demand_id == card.id, DemandUpdate.kind == "WARNING_ACKNOWLEDGED"
                )
            ).all()
        )
        == 2
    )
