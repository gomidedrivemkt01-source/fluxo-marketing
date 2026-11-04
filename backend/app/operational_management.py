"""Transactional administration of assignments and historical references."""

import math
import uuid
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.api.demands import (
    ensure_demand_stage_instances,
    ensure_workflow_version,
    record_stage_visit_transition,
    version_stage,
)
from app.api.errors import ApiError
from app.auth.service import Principal
from app.models import (
    AppSession,
    AuditEvent,
    AuthAccount,
    CategoryTemplateBinding,
    Demand,
    DemandCategory,
    DemandStageInstance,
    DemandUpdate,
    JobRole,
    MemberJobRole,
    MemberRoleAssignment,
    Membership,
    MembershipStatus,
    TimeEntry,
    UserProfile,
    Workflow,
    WorkflowStage,
    WorkflowVersion,
    utc_now,
)


class RoleChange(BaseModel):
    role_id: uuid.UUID = Field(alias="roleId")
    primary_profile_id: uuid.UUID | None = Field(alias="primaryProfileId")
    fallback_profile_id: uuid.UUID | None = Field(alias="fallbackProfileId")
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class StageChange(BaseModel):
    stage_id: uuid.UUID = Field(alias="stageId")
    owner_role_id: uuid.UUID | None = Field(alias="ownerRoleId")
    primary_profile_id: uuid.UUID | None = Field(alias="primaryProfileId")
    fallback_profile_id: uuid.UUID | None = Field(alias="fallbackProfileId")
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class ResponsibilityChange(BaseModel):
    roles: list[RoleChange] = Field(default_factory=list, max_length=100)
    stages: list[StageChange] = Field(default_factory=list, max_length=500)
    apply_to_current: bool = Field(default=False, alias="applyToCurrent")
    apply_to_future: bool = Field(default=True, alias="applyToFuture")

    @model_validator(mode="after")
    def validate_unique(self) -> "ResponsibilityChange":
        if not self.roles and not self.stages:
            raise ValueError("Escolha ao menos uma função ou etapa.")
        if len({r.role_id for r in self.roles}) != len(self.roles):
            raise ValueError("Função repetida.")
        if len({s.stage_id for s in self.stages}) != len(self.stages):
            raise ValueError("Etapa repetida.")
        all_changes: list[RoleChange | StageChange] = [*self.roles, *self.stages]
        for item in all_changes:
            if item.primary_profile_id and item.primary_profile_id == item.fallback_profile_id:
                raise ValueError("O principal e o substituto devem ser pessoas diferentes.")
        return self


def audit(db: Session, principal: Principal, event: str, data: dict[str, Any]) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type=event,
            source="interface",
            metadata_json=data,
        )
    )


def active_people(db: Session, organization_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(Membership.user_profile_id).where(
                Membership.organization_id == organization_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.removed_at.is_(None),
            )
        )
    )


def current_roles(
    db: Session, organization_id: uuid.UUID
) -> dict[uuid.UUID | None, dict[str, uuid.UUID | None]]:
    rows = db.execute(
        select(MemberRoleAssignment, Membership.user_profile_id)
        .join(Membership, Membership.id == MemberRoleAssignment.membership_id)
        .join(JobRole, JobRole.id == MemberRoleAssignment.job_role_id)
        .where(
            MemberRoleAssignment.organization_id == organization_id,
            MemberRoleAssignment.active.is_(True),
            JobRole.active.is_(True),
            Membership.status == MembershipStatus.ACTIVE,
            Membership.removed_at.is_(None),
        )
        .order_by(MemberRoleAssignment.priority, MemberRoleAssignment.created_at)
    ).all()
    result: dict[uuid.UUID | None, dict[str, uuid.UUID | None]] = {}
    now = utc_now()
    for assignment, profile_id in rows:
        if assignment.valid_from and assignment.valid_from > now:
            continue
        if assignment.valid_until and assignment.valid_until < now:
            continue
        key = "fallback" if assignment.is_fallback else "primary"
        result.setdefault(assignment.job_role_id, {}).setdefault(key, profile_id)
    return result


def resolve_assignment(
    snapshot: dict[str, Any],
    roles: dict[uuid.UUID | None, dict[str, uuid.UUID | None]],
    people: set[uuid.UUID],
    demand: Demand,
) -> uuid.UUID | None:
    def identifier(key: str) -> uuid.UUID | None:
        return uuid.UUID(str(snapshot[key])) if snapshot.get(key) else None

    direct = identifier("defaultAssigneeId")
    if direct in people:
        return direct
    role_id = identifier("ownerRoleId")
    members = roles.get(role_id, {})
    for candidate in (
        members.get("primary"),
        members.get("fallback"),
        identifier("fallbackUserId"),
    ):
        if candidate in people:
            return candidate
    return None


def role_stage_snapshot(stage: WorkflowStage) -> dict[str, Any]:
    return {
        "defaultAssigneeId": str(stage.default_assignee_id) if stage.default_assignee_id else None,
        "ownerRoleId": str(stage.owner_role_id) if stage.owner_role_id else None,
        "fallbackUserId": str(stage.fallback_user_id) if stage.fallback_user_id else None,
    }


def responsibility_plan(
    db: Session, principal: Principal, payload: ResponsibilityChange, *, lock: bool = False
) -> tuple[
    dict[str, Any],
    list[
        tuple[
            Demand,
            DemandStageInstance | None,
            bool,
            uuid.UUID | None,
            uuid.UUID,
            dict[str, Any] | None,
        ]
    ],
    dict[uuid.UUID, JobRole],
    dict[uuid.UUID, WorkflowStage],
]:
    org = principal.membership.organization_id
    people = active_people(db, org)
    all_changes: list[RoleChange | StageChange] = [*payload.roles, *payload.stages]
    chosen = {
        p for item in all_changes for p in (item.primary_profile_id, item.fallback_profile_id) if p
    }
    if not chosen <= people:
        raise ApiError(422, "assignee_invalid", "Escolha apenas integrantes ativos da equipe.")
    roles = {
        item.id: item
        for item in db.scalars(
            select(JobRole)
            .where(JobRole.organization_id == org, JobRole.active.is_(True))
            .with_for_update()
            if lock
            else select(JobRole).where(JobRole.organization_id == org, JobRole.active.is_(True))
        )
    }
    stages = {
        item.id: item
        for item in db.scalars(
            select(WorkflowStage)
            .where(WorkflowStage.organization_id == org, WorkflowStage.removed_at.is_(None))
            .with_for_update()
            if lock
            else select(WorkflowStage).where(
                WorkflowStage.organization_id == org, WorkflowStage.removed_at.is_(None)
            )
        )
    }
    before_roles = current_roles(db, org)
    after_roles = {key: dict(value) for key, value in before_roles.items()}
    role_changes = {item.role_id: item for item in payload.roles}
    stage_changes = {item.stage_id: item for item in payload.stages}
    for change in payload.roles:
        role = roles.get(change.role_id)
        if not role or role.revision != change.expected_revision:
            raise ApiError(409, "revision_conflict", "Uma função foi alterada. Atualize a tela.")
        after_roles[role.id] = {
            "primary": change.primary_profile_id,
            "fallback": change.fallback_profile_id,
        }
    for stage_change in payload.stages:
        stage = stages.get(stage_change.stage_id)
        if not stage or stage.revision != stage_change.expected_revision:
            raise ApiError(409, "revision_conflict", "Uma etapa foi alterada. Atualize a tela.")
        if stage_change.owner_role_id and stage_change.owner_role_id not in roles:
            raise ApiError(422, "role_invalid", "Função operacional indisponível.")
    affected = [
        s for s in stages.values() if s.id in stage_changes or s.owner_role_id in role_changes
    ]
    # Include frozen versions: a card can still use a function removed from its live template.
    version_rows = list(
        db.scalars(select(WorkflowVersion).where(WorkflowVersion.organization_id == org))
    )
    versions = {v.id: v for v in version_rows}
    related_versions = {
        v.id
        for v in version_rows
        if any(
            uuid.UUID(s["ownerRoleId"]) in role_changes if s.get("ownerRoleId") else False
            for s in v.definition.get("stages", [])
        )
        or any(uuid.UUID(s["id"]) in stage_changes for s in v.definition.get("stages", []))
    }
    query = (
        select(Demand)
        .where(
            Demand.organization_id == org,
            Demand.deleted_at.is_(None),
            Demand.status != "COMPLETED",
            or_(
                Demand.workflow_version_id.in_(related_versions),
                Demand.id.in_(
                    select(DemandStageInstance.demand_id).where(
                        DemandStageInstance.organization_id == org,
                        DemandStageInstance.assignment_defaults["ownerRoleId"].astext.in_(
                            [str(key) for key in role_changes]
                        ),
                    )
                ),
            ),
        )
        .order_by(Demand.id)
    )
    cards = list(db.scalars(query.with_for_update() if lock else query))
    instances = list(
        db.scalars(
            select(DemandStageInstance)
            .where(DemandStageInstance.demand_id.in_([d.id for d in cards]))
            .with_for_update()
            if lock
            else select(DemandStageInstance).where(
                DemandStageInstance.demand_id.in_([d.id for d in cards])
            )
        )
    )
    by_card: dict[uuid.UUID, list[DemandStageInstance]] = {}
    for stored_instance in instances:
        by_card.setdefault(stored_instance.demand_id, []).append(stored_instance)
    changes: list[
        tuple[
            Demand,
            DemandStageInstance | None,
            bool,
            uuid.UUID | None,
            uuid.UUID,
            dict[str, Any] | None,
        ]
    ] = []
    for card in cards:
        assert card.workflow_version_id is not None
        version = versions[card.workflow_version_id]
        for snapshot in version.definition.get("stages", []):
            stage_id = uuid.UUID(snapshot["id"])
            current = card.current_stage_id == stage_id
            instance = next(
                (
                    i
                    for i in by_card.get(card.id, [])
                    if i.workflow_version_id == version.id and i.workflow_stage_id == stage_id
                ),
                None,
            )
            effective = (
                {**snapshot, **(instance.assignment_defaults or {})} if instance else snapshot
            )
            role_id = uuid.UUID(effective["ownerRoleId"]) if effective.get("ownerRoleId") else None
            if stage_id not in stage_changes and role_id not in role_changes:
                continue
            if not current and (
                not payload.apply_to_future or (instance and instance.state != "upcoming")
            ):
                continue
            if current and not payload.apply_to_current:
                continue
            # An explicit assignment on a card is not a default assignment.
            old_default = resolve_assignment(effective, before_roles, people, card)
            actual = (
                card.current_assignee_id if current else instance.assignee_id if instance else None
            )
            manual = actual is not None and actual != old_default
            changed_snapshot = dict(effective)
            explicit = stage_changes.get(stage_id)
            if explicit:
                changed_snapshot.update(
                    defaultAssigneeId=str(explicit.primary_profile_id)
                    if explicit.primary_profile_id
                    else None,
                    ownerRoleId=str(explicit.owner_role_id) if explicit.owner_role_id else None,
                    fallbackUserId=str(explicit.fallback_profile_id)
                    if explicit.fallback_profile_id
                    else None,
                )
            target = (
                actual
                if manual
                else resolve_assignment(changed_snapshot, after_roles, people, card)
            )
            defaults = (
                {
                    key: changed_snapshot.get(key)
                    for key in ("ownerRoleId", "defaultAssigneeId", "fallbackUserId")
                }
                if explicit
                else None
            )
            if target != actual or defaults is not None:
                changes.append((card, instance, current, target, stage_id, defaults))
    current_ids = {
        card.id
        for card, _, current, target, _, _ in changes
        if current and target != card.current_assignee_id
    }
    running = list(
        db.scalars(
            select(TimeEntry.demand_id).where(
                TimeEntry.organization_id == org,
                TimeEntry.demand_id.in_(current_ids),
                TimeEntry.state == "RUNNING",
                TimeEntry.deleted_at.is_(None),
            )
        )
    )
    preview = {
        "roles": len(payload.roles),
        "stages": len(affected),
        "currentDemands": len(current_ids),
        "futureStages": sum(not item[2] for item in changes),
        "runningTimers": len(set(running)),
        "affectedStages": [
            {"id": str(s.id), "name": s.name, "workflowId": str(s.workflow_id)} for s in affected
        ],
        "demands": [
            {"id": str(d.id), "publicId": d.public_id, "title": d.title}
            for d in cards
            if d.id in current_ids
        ],
    }
    return preview, changes, roles, stages


def apply_responsibilities(
    db: Session, principal: Principal, payload: ResponsibilityChange, *, commit: bool = True
) -> dict[str, Any]:
    preview, changes, roles, stages = responsibility_plan(db, principal, payload, lock=True)
    if preview["runningTimers"]:
        raise ApiError(
            409, "running_timers", "Pause os timers das demandas afetadas antes de redistribuir."
        )
    org = principal.membership.organization_id
    before = {
        "roles": {
            str(key): {mode: str(value) if value else None for mode, value in people.items()}
            for key, people in current_roles(db, org).items()
        },
        "stages": {
            str(change.stage_id): role_stage_snapshot(stages[change.stage_id])
            for change in payload.stages
        },
    }
    memberships = {
        m.user_profile_id: m
        for m in db.scalars(
            select(Membership).where(
                Membership.organization_id == org,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.removed_at.is_(None),
            )
        )
    }
    now = utc_now()
    for change in payload.roles:
        rows = list(
            db.scalars(
                select(MemberRoleAssignment)
                .where(
                    MemberRoleAssignment.organization_id == org,
                    MemberRoleAssignment.job_role_id == change.role_id,
                )
                .with_for_update()
            )
        )
        for previous_assignment in rows:
            previous_assignment.active = False
            previous_assignment.revision += 1
        for profile_id, fallback in (
            (change.primary_profile_id, False),
            (change.fallback_profile_id, True),
        ):
            if profile_id is None:
                continue
            membership = memberships[profile_id]
            row = next((r for r in rows if r.membership_id == membership.id), None)
            if row is None:
                row = MemberRoleAssignment(
                    organization_id=org, membership_id=membership.id, job_role_id=change.role_id
                )
                db.add(row)
            row.active, row.is_fallback, row.priority = True, fallback, 20 if fallback else 10
            row.valid_from = row.valid_until = None
            row.updated_at = now
        roles[change.role_id].revision += 1
    for stage_change in payload.stages:
        stage = stages[stage_change.stage_id]
        stage.owner_role_id = stage_change.owner_role_id
        stage.default_assignee_id = stage_change.primary_profile_id
        stage.fallback_user_id = stage_change.fallback_profile_id
        stage.revision += 1
        stage.updated_at = now
    for card, instance, current, target, stage_id, defaults in changes:
        if instance is None and card.workflow_version_id:
            version = db.get(WorkflowVersion, card.workflow_version_id)
            if version:
                instance = next(
                    (
                        i
                        for i in ensure_demand_stage_instances(db, card, version)
                        if i.workflow_stage_id == stage_id
                    ),
                    None,
                )
        if instance:
            if defaults is not None:
                instance.assignment_defaults = defaults
            instance.assignee_id = target
            instance.revision += 1
            instance.updated_at = now
        if current and card.current_assignee_id != target:
            previous = card.current_assignee_id
            card.current_assignee_id = target
            card.revision += 1
            card.updated_at = now
            record_stage_visit_transition(
                db,
                card,
                actor_id=principal.profile.id,
                from_stage_id=stage_id,
                to_stage_id=stage_id,
                action="REASSIGN",
                moved_at=now,
                reason="Responsabilidade atualizada em massa pela administração.",
                source="management",
            )
            db.add(
                DemandUpdate(
                    demand_id=card.id,
                    created_by=principal.profile.id,
                    kind="ASSIGNEE_CHANGED",
                    summary="Responsável atualizado pela gestão de funções.",
                    payload={
                        "previousAssigneeId": str(previous) if previous else None,
                        "assigneeId": str(target) if target else None,
                        "source": "management",
                    },
                )
            )
    audit(
        db,
        principal,
        "RESPONSIBILITIES_UPDATED",
        {
            "preview": preview,
            "before": before,
            "changes": payload.model_dump(mode="json", by_alias=True),
        },
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return preview


def find_workflow(db: Session, org: uuid.UUID, workflow_id: uuid.UUID) -> Workflow:
    workflow = db.scalar(
        select(Workflow)
        .where(
            Workflow.id == workflow_id,
            Workflow.organization_id == org,
            Workflow.removed_at.is_(None),
        )
        .with_for_update()
    )
    if not workflow:
        raise ApiError(404, "workflow_not_found", "Workflow não encontrado.")
    return workflow


def live_stages(db: Session, org: uuid.UUID, workflow_id: uuid.UUID) -> list[WorkflowStage]:
    return list(
        db.scalars(
            select(WorkflowStage)
            .where(
                WorkflowStage.organization_id == org,
                WorkflowStage.workflow_id == workflow_id,
                WorkflowStage.active.is_(True),
                WorkflowStage.removed_at.is_(None),
            )
            .order_by(WorkflowStage.position)
        )
    )


def removal_preview(
    db: Session, principal: Principal, workflow_id: uuid.UUID, stage_id: uuid.UUID | None = None
) -> dict[str, Any]:
    org = principal.membership.organization_id
    workflow = find_workflow(db, org, workflow_id)
    if stage_id:
        stage = db.scalar(
            select(WorkflowStage)
            .where(
                WorkflowStage.id == stage_id,
                WorkflowStage.workflow_id == workflow.id,
                WorkflowStage.organization_id == org,
                WorkflowStage.removed_at.is_(None),
            )
            .with_for_update()
        )
        if not stage:
            raise ApiError(404, "stage_not_found", "Etapa não encontrada.")
        targets = [s for s in live_stages(db, org, workflow.id) if s.id != stage_id]
        target_workflow = workflow
    else:
        if workflow.is_default:
            raise ApiError(
                409, "default_workflow_required", "O workflow padrão não pode ser excluído."
            )
        default_workflow = db.scalar(
            select(Workflow).where(
                Workflow.organization_id == org,
                Workflow.is_default.is_(True),
                Workflow.active.is_(True),
                Workflow.removed_at.is_(None),
            )
        )
        if default_workflow is None:
            raise ApiError(
                409,
                "default_workflow_required",
                "Defina um workflow padrão ativo antes de excluir.",
            )
        target_workflow = default_workflow
        targets = live_stages(db, org, target_workflow.id)
    if not targets:
        raise ApiError(
            409, "workflow_requires_active_stage", "O destino precisa ter ao menos uma etapa ativa."
        )
    cards = list(
        db.scalars(
            select(Demand)
            .where(
                Demand.organization_id == org,
                Demand.workflow_id == workflow.id,
                Demand.deleted_at.is_(None),
            )
            .order_by(Demand.id)
            .with_for_update()
        )
    )
    affected = [d for d in cards if stage_id is None or d.current_stage_id == stage_id]
    running = list(
        db.scalars(
            select(TimeEntry.demand_id).where(
                TimeEntry.demand_id.in_([d.id for d in cards]),
                TimeEntry.state == "RUNNING",
                TimeEntry.deleted_at.is_(None),
            )
        )
    )
    categories = (
        list(
            db.scalars(
                select(DemandCategory).where(
                    DemandCategory.organization_id == org,
                    DemandCategory.default_workflow_id == workflow.id,
                )
            )
        )
        if stage_id is None
        else []
    )
    return {
        "workflowId": str(workflow.id),
        "workflowName": workflow.name,
        "targetWorkflowId": str(target_workflow.id),
        "targetWorkflowName": target_workflow.name,
        "currentDemands": len(affected),
        "migratedDemands": len(cards),
        "categories": len(categories),
        "runningTimers": len(set(running)),
        "revision": stage.revision if stage_id and stage else workflow.revision,
        "targets": [{"id": str(s.id), "name": s.name} for s in targets],
    }


def migrate_card(
    db: Session,
    principal: Principal,
    card: Demand,
    workflow: Workflow,
    version: WorkflowVersion,
    target: WorkflowStage,
    reason: str,
) -> None:
    now = utc_now()
    old_stage_id, old_workflow_id = card.current_stage_id, card.workflow_id
    old_version = (
        db.get(WorkflowVersion, card.workflow_version_id) if card.workflow_version_id else None
    )
    old_instances = list(
        db.scalars(
            select(DemandStageInstance)
            .where(
                DemandStageInstance.demand_id == card.id,
                DemandStageInstance.workflow_version_id == card.workflow_version_id,
            )
            .with_for_update()
        )
    )
    old_by_code = {
        str((version_stage(old_version, i.workflow_stage_id) or {}).get("code")): i
        for i in old_instances
    }
    card.workflow_id, card.workflow_version_id, card.current_stage_id = (
        workflow.id,
        version.id,
        target.id,
    )
    instances = ensure_demand_stage_instances(db, card, version)
    people = active_people(db, card.organization_id)
    roles = current_roles(db, card.organization_id)
    for instance in instances:
        snap = version_stage(version, instance.workflow_stage_id) or {}
        old = old_by_code.get(str(snap.get("code")))
        if old and old is not instance:
            instance.assignee_id, instance.deadline_at, instance.forecast_at = (
                old.assignee_id,
                old.deadline_at,
                old.forecast_at,
            )
            instance.state, instance.entered_at, instance.left_at = (
                old.state,
                old.entered_at,
                old.left_at,
            )
        if instance.workflow_stage_id == target.id:
            instance.state = "completed" if card.status == "COMPLETED" else "current"
            instance.assignee_id = (
                card.current_assignee_id
                if old_stage_id == target.id and card.current_assignee_id in people
                else resolve_assignment(snap, roles, people, card)
            )
            instance.entered_at = instance.entered_at or now
            instance.forecast_at = card.forecast_at
            card.current_assignee_id = instance.assignee_id
        elif instance.state == "current":
            instance.state = "upcoming"
    if card.status != "COMPLETED":
        record_stage_visit_transition(
            db,
            card,
            actor_id=principal.profile.id,
            from_stage_id=old_stage_id,
            to_stage_id=target.id,
            action="MIGRATE",
            moved_at=now,
            reason=reason,
            source="management",
        )
    card.revision += 1
    card.updated_at = now
    db.add(
        DemandUpdate(
            demand_id=card.id,
            created_by=principal.profile.id,
            kind="WORKFLOW_MIGRATED",
            summary=reason,
            payload={
                "fromWorkflowId": str(old_workflow_id),
                "toWorkflowId": str(workflow.id),
                "fromStageId": str(old_stage_id),
                "toStageId": str(target.id),
            },
        )
    )


def remove_workflow_or_stage(
    db: Session,
    principal: Principal,
    workflow_id: uuid.UUID,
    revision: int,
    *,
    stage_id: uuid.UUID | None = None,
    target_stage_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    preview = removal_preview(db, principal, workflow_id, stage_id)
    if preview["revision"] != revision:
        raise ApiError(409, "revision_conflict", "O modelo foi alterado. Atualize a tela.")
    if preview["runningTimers"]:
        raise ApiError(
            409, "running_timers", "Pause os timers deste fluxo antes de excluir ou migrar etapas."
        )
    org = principal.membership.organization_id
    workflow = find_workflow(db, org, workflow_id)
    target_workflow = find_workflow(db, org, uuid.UUID(preview["targetWorkflowId"]))
    targets = live_stages(db, org, target_workflow.id)
    stage = db.get(WorkflowStage, stage_id) if stage_id else None
    if stage:
        targets = [s for s in targets if s.id != stage.id]
        if target_stage_id not in {s.id for s in targets}:
            raise ApiError(422, "target_stage_required", "Escolha a etapa que receberá os cards.")
        stage.active, stage.removed_at = False, utc_now()
        stage.revision += 1
    db.flush()
    version = ensure_workflow_version(db, org, target_workflow.id, principal.profile.id)
    cards = list(
        db.scalars(
            select(Demand)
            .where(
                Demand.organization_id == org,
                Demand.workflow_id == workflow.id,
                Demand.deleted_at.is_(None),
            )
            .order_by(Demand.id)
            .with_for_update()
        )
    )
    for card in cards:
        old = db.get(WorkflowStage, card.current_stage_id) if card.current_stage_id else None
        target = next((s for s in targets if s.id == card.current_stage_id), None)
        if not target:
            target = (
                next((s for s in targets if s.id == target_stage_id), None)
                if stage
                else next((s for s in targets if old and s.code == old.code), targets[0])
            )
        assert target is not None
        reason = (
            f'Etapa "{stage.name}" removida; demanda encaminhada para "{target.name}".'
            if stage
            else f'Workflow "{workflow.name}" removido; demanda transferida para "{target_workflow.name}" / "{target.name}".'
        )
        migrate_card(db, principal, card, target_workflow, version, target, reason)
    if not stage:
        categories = list(
            db.scalars(
                select(DemandCategory)
                .where(
                    DemandCategory.organization_id == org,
                    DemandCategory.default_workflow_id == workflow.id,
                )
                .with_for_update()
            )
        )
        for category in categories:
            category.default_workflow_id = target_workflow.id
            category.revision += 1
        workflow.active, workflow.removed_at, workflow.lifecycle_state = False, utc_now(), "RETIRED"
        for retired_stage in db.scalars(
            select(WorkflowStage).where(WorkflowStage.workflow_id == workflow.id)
        ):
            retired_stage.active, retired_stage.removed_at = False, utc_now()
            retired_stage.revision += 1
    # Both stage and workflow removal publish a new category binding.
    bindings = list(
        db.scalars(
            select(CategoryTemplateBinding)
            .join(
                WorkflowVersion, WorkflowVersion.id == CategoryTemplateBinding.workflow_version_id
            )
            .where(
                CategoryTemplateBinding.organization_id == org,
                WorkflowVersion.workflow_id == workflow.id,
                CategoryTemplateBinding.effective_until.is_(None),
            )
            .with_for_update()
        )
    )
    changed_at = utc_now()
    for binding in bindings:
        binding.effective_until = changed_at
    db.flush()  # Release the partial unique index before adding replacement bindings.
    for binding in bindings:
        db.add(
            CategoryTemplateBinding(
                organization_id=org,
                category_id=binding.category_id,
                workflow_version_id=version.id,
                briefing_template_version_id=binding.briefing_template_version_id,
                effective_from=changed_at,
                activated_by=principal.profile.id,
            )
        )
    workflow.revision += 1
    workflow.updated_at = utc_now()
    audit(db, principal, "WORKFLOW_STAGE_REMOVED" if stage else "WORKFLOW_REMOVED", preview)
    db.commit()
    return {"deleted": True, **preview}


def remove_person(
    db: Session, principal: Principal, membership_id: uuid.UUID, revision: int
) -> dict[str, Any]:
    org = principal.membership.organization_id
    member = db.scalar(
        select(Membership)
        .where(
            Membership.organization_id == org,
            Membership.id == membership_id,
            Membership.removed_at.is_(None),
        )
        .with_for_update()
    )
    if not member:
        raise ApiError(404, "user_not_found", "Pessoa não encontrada.")
    if member.id == principal.membership.id:
        raise ApiError(
            409, "self_removal", "Seu cadastro deve ser gerenciado por outro administrador."
        )
    if member.revision != revision:
        raise ApiError(409, "revision_conflict", "O cadastro foi alterado. Atualize a tela.")
    if member.status != MembershipStatus.SUSPENDED:
        raise ApiError(
            409, "suspend_first", "Remova o acesso da pessoa antes de excluir o cadastro."
        )
    profile = db.get(UserProfile, member.user_profile_id)
    if profile is None:
        raise ApiError(404, "profile_not_found", "Perfil não encontrado.")
    now = utc_now()
    for entry in db.scalars(
        select(TimeEntry)
        .where(
            TimeEntry.organization_id == org,
            TimeEntry.user_profile_id == profile.id,
            TimeEntry.state.in_(["RUNNING", "PAUSED"]),
            TimeEntry.deleted_at.is_(None),
        )
        .with_for_update()
    ):
        if entry.state == "RUNNING":
            entry.duration_minutes = (entry.duration_minutes or 0) + max(
                1, math.ceil((now - entry.started_at).total_seconds() / 60)
            )
        entry.state, entry.ended_at, entry.updated_at = "COMPLETED", now, now
        entry.revision += 1
    for assignment in db.scalars(
        select(MemberRoleAssignment)
        .where(
            MemberRoleAssignment.organization_id == org,
            MemberRoleAssignment.membership_id == member.id,
        )
        .with_for_update()
    ):
        assignment.active = False
        assignment.revision += 1
    db.execute(delete(MemberJobRole).where(MemberJobRole.membership_id == member.id))
    stages = list(
        db.scalars(
            select(WorkflowStage)
            .where(WorkflowStage.organization_id == org, WorkflowStage.removed_at.is_(None))
            .with_for_update()
        )
    )
    for stage in stages:
        changed = stage.default_assignee_id == profile.id or stage.fallback_user_id == profile.id
        if stage.default_assignee_id == profile.id:
            stage.default_assignee_id = (
                stage.fallback_user_id if stage.fallback_user_id != profile.id else None
            )
            stage.fallback_user_id = None
        elif stage.fallback_user_id == profile.id:
            stage.fallback_user_id = None
        if changed:
            stage.revision += 1
    db.flush()
    people, roles = active_people(db, org), current_roles(db, org)
    instances = list(
        db.scalars(
            select(DemandStageInstance)
            .join(Demand, Demand.id == DemandStageInstance.demand_id)
            .where(
                Demand.organization_id == org,
                Demand.deleted_at.is_(None),
                Demand.status != "COMPLETED",
                DemandStageInstance.workflow_version_id == Demand.workflow_version_id,
                DemandStageInstance.assignee_id == profile.id,
                DemandStageInstance.state.in_(["current", "upcoming"]),
            )
            .with_for_update()
        )
    )
    for instance in instances:
        assigned_stage = next((s for s in stages if s.id == instance.workflow_stage_id), None)
        card = db.get(Demand, instance.demand_id)
        assert card is not None
        instance.assignee_id = (
            resolve_assignment(role_stage_snapshot(assigned_stage), roles, people, card)
            if assigned_stage
            else None
        )
        instance.revision += 1
    cards = list(
        db.scalars(
            select(Demand)
            .where(
                Demand.organization_id == org,
                Demand.deleted_at.is_(None),
                Demand.status != "COMPLETED",
                Demand.current_assignee_id == profile.id,
            )
            .order_by(Demand.id)
            .with_for_update()
        )
    )
    for card in cards:
        current_stage = next((s for s in stages if s.id == card.current_stage_id), None)
        card.current_assignee_id = (
            resolve_assignment(role_stage_snapshot(current_stage), roles, people, card)
            if current_stage
            else None
        )
        card.revision += 1
        card.updated_at = now
        record_stage_visit_transition(
            db,
            card,
            actor_id=principal.profile.id,
            from_stage_id=card.current_stage_id,
            to_stage_id=card.current_stage_id,
            action="REASSIGN",
            moved_at=now,
            reason=f"Cadastro de {profile.full_name} removido da equipe.",
            source="management",
        )
        db.add(
            DemandUpdate(
                demand_id=card.id,
                created_by=principal.profile.id,
                kind="ASSIGNEE_CHANGED",
                summary=f"Cadastro de {profile.full_name} removido; responsabilidade redistribuída.",
                payload={
                    "previousAssigneeId": str(profile.id),
                    "assigneeId": str(card.current_assignee_id)
                    if card.current_assignee_id
                    else None,
                },
            )
        )
    member.removed_at, member.revision = now, member.revision + 1
    db.execute(
        update(AppSession).where(AppSession.user_profile_id == profile.id).values(revoked_at=now)
    )
    other_membership = db.scalar(
        select(Membership.id).where(
            Membership.user_profile_id == profile.id,
            Membership.id != member.id,
            Membership.removed_at.is_(None),
        )
    )
    if not other_membership:
        account = db.get(AuthAccount, profile.auth_user_id)
        if account:
            db.delete(account)
        profile.email = f"removed-{profile.id}@removed.invalid"
        profile.avatar_data = profile.avatar_path = profile.avatar_content_type = None
        profile.workspace_preferences = {}
        profile.revision += 1
    audit(
        db,
        principal,
        "MEMBER_REMOVED",
        {
            "membershipId": str(member.id),
            "profileId": str(profile.id),
            "name": profile.full_name,
            "reassignedDemands": len(cards),
        },
    )
    db.commit()
    return {"removed": True, "reassignedDemands": len(cards), "historyPreserved": True}
