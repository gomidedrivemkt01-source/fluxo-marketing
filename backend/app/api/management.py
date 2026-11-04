import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.access import require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import WorkflowStage
from app.operational_management import (
    ResponsibilityChange,
    apply_responsibilities,
    removal_preview,
    remove_person,
    remove_workflow_or_stage,
    responsibility_plan,
)

router = APIRouter(prefix="/management", tags=["Gestão operacional"])


@router.post("/responsibilities/preview", dependencies=[Depends(require_csrf)])
def preview_responsibilities(
    payload: ResponsibilityChange,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_permission(principal, "catalog:write")
    return responsibility_plan(db, principal, payload)[0]


@router.post("/responsibilities", dependencies=[Depends(require_csrf)])
def save_responsibilities(
    payload: ResponsibilityChange,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_permission(principal, "catalog:write")
    return apply_responsibilities(db, principal, payload)


@router.get("/workflows/{workflow_id}/removal-preview")
def preview_workflow_removal(
    workflow_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_permission(principal, "catalog:write")
    return removal_preview(db, principal, workflow_id)


@router.get("/stages/{stage_id}/removal-preview")
def preview_stage_removal(
    stage_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_permission(principal, "catalog:write")
    stage = db.get(WorkflowStage, stage_id)
    if (
        not stage
        or not stage.workflow_id
        or stage.organization_id != principal.membership.organization_id
        or stage.removed_at
    ):
        raise ApiError(404, "stage_not_found", "Etapa não encontrada.")
    return removal_preview(db, principal, stage.workflow_id, stage.id)


@router.delete("/stages/{stage_id}", dependencies=[Depends(require_csrf)])
def remove_stage(
    stage_id: uuid.UUID,
    expected_revision: int = Query(alias="expectedRevision", ge=1),
    target_stage_id: uuid.UUID = Query(alias="targetStageId"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_permission(principal, "catalog:write")
    stage = db.get(WorkflowStage, stage_id)
    if (
        not stage
        or not stage.workflow_id
        or stage.organization_id != principal.membership.organization_id
        or stage.removed_at
    ):
        raise ApiError(404, "stage_not_found", "Etapa não encontrada.")
    return remove_workflow_or_stage(
        db,
        principal,
        stage.workflow_id,
        expected_revision,
        stage_id=stage_id,
        target_stage_id=target_stage_id,
    )


@router.delete("/people/{membership_id}", dependencies=[Depends(require_csrf)])
def remove_member(
    membership_id: uuid.UUID,
    expected_revision: int = Query(alias="expectedRevision", ge=1),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_permission(principal, "users:manage")
    if not principal.role or principal.role.code != "admin":
        raise ApiError(403, "admin_required", "Somente administradores podem excluir pessoas.")
    return remove_person(db, principal, membership_id, expected_revision)
