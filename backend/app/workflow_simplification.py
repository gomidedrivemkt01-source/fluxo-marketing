"""Audited, repeatable configuration of stage functions without deleting history."""

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.demands import ensure_workflow_version
from app.auth.service import Principal
from app.models import (
    ChecklistTemplateItem,
    JobRole,
    Membership,
    MembershipStatus,
    UserProfile,
    Workflow,
    WorkflowStage,
    utc_now,
)
from app.operational_management import (
    ResponsibilityChange,
    apply_responsibilities,
    audit,
    current_roles,
    responsibility_plan,
)


class FunctionConfiguration(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    primary_name: str = Field(alias="primaryName")
    fallback_name: str = Field(alias="fallbackName")


class StageConfiguration(BaseModel):
    workflow_code: str = Field(alias="workflowCode")
    stage_code: str = Field(alias="stageCode")
    function_code: str = Field(alias="functionCode")


class WorkflowSimplification(BaseModel):
    functions: list[FunctionConfiguration] = Field(min_length=1, max_length=100)
    stages: list[StageConfiguration] = Field(min_length=1, max_length=500)


def simplify_workflows(
    db: Session, principal: Principal, config: WorkflowSimplification, *, apply: bool = False
) -> dict[str, Any]:
    """Caller owns the transaction; preview creations must always be rolled back."""
    org = principal.membership.organization_id
    people: dict[str, list[uuid.UUID]] = {}
    for person in db.scalars(
        select(UserProfile)
        .join(Membership)
        .where(
            Membership.organization_id == org,
            Membership.status == MembershipStatus.ACTIVE,
            Membership.removed_at.is_(None),
        )
    ):
        people.setdefault(person.full_name.strip().casefold(), []).append(person.id)

    def person_id(name: str) -> uuid.UUID:
        matches = people.get(name.strip().casefold(), [])
        if len(matches) != 1:
            raise ValueError(f"Integrante ativo ausente ou ambíguo: {name}.")
        return matches[0]

    old_assignments = current_roles(db, org)
    roles = list(db.scalars(select(JobRole).where(JobRole.organization_id == org)))
    functions: dict[str, JobRole] = {}
    created_roles: list[str] = []
    renamed_roles: list[dict[str, str]] = []
    role_changes: list[dict[str, Any]] = []
    for entry in config.functions:
        if entry.code in functions:
            raise ValueError(f"Função repetida: {entry.code}.")
        primary, fallback = person_id(entry.primary_name), person_id(entry.fallback_name)
        if primary == fallback:
            raise ValueError("Principal e substituto devem ser pessoas diferentes.")
        role = next((r for r in roles if r.code == entry.code), None)
        named = next((r for r in roles if r.name.casefold() == entry.name.casefold()), None)
        if named is not None and named is not role:
            raise ValueError(f"Nome de função já associado a outro código: {entry.name}.")
        if role is None:
            role = JobRole(organization_id=org, code=entry.code, name=entry.name, active=True)
            db.add(role)
            db.flush()
            roles.append(role)
            created_roles.append(entry.code)
        if not role.active:
            raise ValueError(f"Função inativa: {entry.code}. Reative-a antes de continuar.")
        if role.name != entry.name:
            renamed_roles.append({"id": str(role.id), "before": role.name, "after": entry.name})
        functions[entry.code] = role
        previous = old_assignments.get(role.id, {})
        if previous.get("primary") != primary or previous.get("fallback") != fallback:
            role_changes.append(
                {
                    "roleId": role.id,
                    "primaryProfileId": primary,
                    "fallbackProfileId": fallback,
                    "expectedRevision": role.revision,
                }
            )

    stages = {
        (workflow.code, stage.code): stage
        for workflow, stage in db.execute(
            select(Workflow, WorkflowStage)
            .join(WorkflowStage)
            .where(
                Workflow.organization_id == org,
                Workflow.active.is_(True),
                Workflow.removed_at.is_(None),
                WorkflowStage.active.is_(True),
                WorkflowStage.removed_at.is_(None),
            )
        )
    }
    stage_changes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for binding in config.stages:
        key = (binding.workflow_code, binding.stage_code)
        if key in seen or key not in stages or binding.function_code not in functions:
            raise ValueError(f"Vínculo de etapa inválido ou repetido: {key}.")
        seen.add(key)
        stage, role = stages[key], functions[binding.function_code]
        if (stage.owner_role_id, stage.default_assignee_id, stage.fallback_user_id) != (
            role.id,
            None,
            None,
        ):
            stage_changes.append(
                {
                    "stageId": stage.id,
                    "ownerRoleId": role.id,
                    "primaryProfileId": None,
                    "fallbackProfileId": None,
                    "expectedRevision": stage.revision,
                }
            )

    items = list(
        db.scalars(
            select(ChecklistTemplateItem).where(
                ChecklistTemplateItem.organization_id == org,
                ChecklistTemplateItem.active.is_(True),
            )
        )
    )
    payload = (
        ResponsibilityChange(
            roles=role_changes, stages=stage_changes, applyToCurrent=True, applyToFuture=True
        )
        if role_changes or stage_changes
        else None
    )
    impact = responsibility_plan(db, principal, payload)[0] if payload else {}
    result = {
        "createdFunctions": created_roles,
        "renamedFunctions": renamed_roles,
        "configuredFunctions": len(functions),
        "linkedStages": len(seen),
        "checklistsDisabled": len(items),
        "responsibilities": impact,
    }
    if not apply:
        return result
    if payload:
        apply_responsibilities(db, principal, payload, commit=False)
    for entry in config.functions:
        role = functions[entry.code]
        if role.name != entry.name:
            role.name = entry.name
            role.revision += 1
    for item in items:
        item.active = False
        item.revision += 1
        item.updated_at = utc_now()
    if payload or items or renamed_roles:
        db.flush()
        for workflow in db.scalars(
            select(Workflow).where(
                Workflow.organization_id == org,
                Workflow.active.is_(True),
                Workflow.removed_at.is_(None),
            )
        ):
            ensure_workflow_version(db, org, workflow.id, principal.profile.id)
        audit(
            db,
            principal,
            "WORKFLOWS_SIMPLIFIED",
            {
                **result,
                "deactivatedTemplateIds": [str(item.id) for item in items],
                "configuration": config.model_dump(mode="json", by_alias=True),
            },
        )
        db.flush()
    return result
