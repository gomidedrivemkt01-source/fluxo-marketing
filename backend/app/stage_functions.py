"""Gestão compartilhada de funções e vínculos entre etapas de mesmo nome."""

import re
import unicodedata
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.service import Principal
from app.models import JobRole, MemberRoleAssignment, Workflow, WorkflowStage
from app.operational_management import (
    ResponsibilityChange,
    RoleChange,
    StageChange,
    apply_responsibilities,
    audit,
    responsibility_plan,
)


def stage_function_key(name: str) -> str:
    value = "".join(
        c for c in unicodedata.normalize("NFKD", name.casefold()) if not unicodedata.combining(c)
    )
    return re.sub(r"[^\w]+", "-", value).strip("-")


class GroupStageRevision(BaseModel):
    id: uuid.UUID
    revision: int = Field(ge=1)


class StageFunctionBinding(BaseModel):
    role_id: uuid.UUID | None = Field(alias="roleId")
    stages: list[GroupStageRevision] = Field(min_length=1, max_length=500)
    apply_to_current: bool = Field(default=True, alias="applyToCurrent")


def grouped_stages(
    db: Session, organization_id: uuid.UUID, *, lock: bool = False
) -> list[tuple[WorkflowStage, Workflow]]:
    statement = (
        select(WorkflowStage, Workflow)
        .join(Workflow, Workflow.id == WorkflowStage.workflow_id)
        .where(
            WorkflowStage.organization_id == organization_id,
            WorkflowStage.removed_at.is_(None),
            WorkflowStage.active.is_(True),
            Workflow.active.is_(True),
            Workflow.removed_at.is_(None),
        )
        .order_by(WorkflowStage.name, Workflow.name, WorkflowStage.id)
    )
    return list(db.execute(statement.with_for_update() if lock else statement).tuples())


def list_stage_function_groups(db: Session, organization_id: uuid.UUID) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for stage, workflow in grouped_stages(db, organization_id):
        key = stage_function_key(stage.name)
        group = groups.setdefault(key, {"key": key, "name": stage.name, "stages": []})
        group["stages"].append(
            {
                "id": str(stage.id),
                "name": stage.name,
                "workflowId": str(workflow.id),
                "workflowName": workflow.name,
                "roleId": str(stage.owner_role_id) if stage.owner_role_id else None,
                "revision": stage.revision,
            }
        )
    for group in groups.values():
        roles = {s["roleId"] for s in group["stages"]}
        group["mixed"] = len(roles) > 1
        group["roleId"] = next(iter(roles)) if len(roles) == 1 else None
    return sorted(groups.values(), key=lambda item: item["key"])


def group_binding_payload(
    db: Session,
    principal: Principal,
    key: str,
    payload: StageFunctionBinding,
    *,
    lock: bool = False,
) -> ResponsibilityChange:
    matching = [
        s
        for s, _ in grouped_stages(db, principal.membership.organization_id, lock=lock)
        if stage_function_key(s.name) == key
    ]
    expected = {item.id: item.revision for item in payload.stages}
    if not matching:
        raise ApiError(404, "stage_group_not_found", "Grupo de etapas não encontrado.")
    if len(expected) != len(payload.stages) or {s.id: s.revision for s in matching} != expected:
        raise ApiError(
            409,
            "revision_conflict",
            "As etapas desse grupo mudaram. Atualize a tela antes de aplicar.",
        )
    return ResponsibilityChange(
        stages=[
            StageChange(
                stageId=stage.id,
                ownerRoleId=payload.role_id,
                primaryProfileId=None if payload.role_id else stage.default_assignee_id,
                fallbackProfileId=None if payload.role_id else stage.fallback_user_id,
                expectedRevision=stage.revision,
            )
            for stage in matching
        ],
        applyToCurrent=payload.apply_to_current,
        applyToFuture=True,
    )


def bind_stage_function(
    db: Session,
    principal: Principal,
    key: str,
    payload: StageFunctionBinding,
    *,
    preview: bool = False,
) -> dict[str, Any]:
    changes = group_binding_payload(db, principal, key, payload, lock=not preview)
    if preview:
        return responsibility_plan(db, principal, changes)[0]
    return apply_responsibilities(db, principal, changes)


def find_job_role(db: Session, principal: Principal, role_id: uuid.UUID) -> JobRole:
    role = db.scalar(
        select(JobRole)
        .where(
            JobRole.id == role_id,
            JobRole.organization_id == principal.membership.organization_id,
            JobRole.active.is_(True),
        )
        .with_for_update()
    )
    if role is None:
        raise ApiError(404, "job_role_not_found", "Função não encontrada.")
    return role


def removal_payload(db: Session, principal: Principal, role: JobRole) -> ResponsibilityChange:
    linked = db.scalars(
        select(WorkflowStage).where(
            WorkflowStage.organization_id == principal.membership.organization_id,
            WorkflowStage.owner_role_id == role.id,
            WorkflowStage.removed_at.is_(None),
        )
    ).all()
    return ResponsibilityChange(
        roles=[
            RoleChange(
                roleId=role.id,
                primaryProfileId=None,
                fallbackProfileId=None,
                expectedRevision=role.revision,
            )
        ],
        stages=[
            StageChange(
                stageId=s.id,
                ownerRoleId=None,
                primaryProfileId=s.default_assignee_id,
                fallbackProfileId=s.fallback_user_id,
                expectedRevision=s.revision,
            )
            for s in linked
        ],
        applyToCurrent=True,
        applyToFuture=True,
    )


def job_role_removal_preview(
    db: Session, principal: Principal, role_id: uuid.UUID
) -> dict[str, Any]:
    role = find_job_role(db, principal, role_id)
    return {
        **responsibility_plan(db, principal, removal_payload(db, principal, role))[0],
        "roleId": str(role.id),
        "roleName": role.name,
        "revision": role.revision,
    }


def remove_job_role(
    db: Session, principal: Principal, role_id: uuid.UUID, expected_revision: int
) -> dict[str, Any]:
    role = find_job_role(db, principal, role_id)
    if role.revision != expected_revision:
        raise ApiError(409, "revision_conflict", "A função foi alterada. Atualize a tela.")
    result = apply_responsibilities(
        db, principal, removal_payload(db, principal, role), commit=False
    )
    role.active = False
    for assignment in db.scalars(
        select(MemberRoleAssignment).where(
            MemberRoleAssignment.organization_id == role.organization_id,
            MemberRoleAssignment.job_role_id == role.id,
            MemberRoleAssignment.active.is_(True),
        )
    ):
        assignment.active = False
        assignment.revision += 1
    audit(
        db,
        principal,
        "JOB_ROLE_REMOVED",
        {
            "id": str(role.id),
            "name": role.name,
            "code": role.code,
            "impact": result,
            "historyPreserved": True,
        },
    )
    # Mantém a identidade histórica inativa e libera nome/código para novo cadastro.
    role.code = f"REMOVED_{role.id.hex}"
    role.name = f"{role.name[:75]} [excluída {role.id.hex[:12]}]"
    db.commit()
    return {"removed": True, "historyPreserved": True, **result}
