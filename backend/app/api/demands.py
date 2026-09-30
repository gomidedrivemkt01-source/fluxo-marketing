import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.api.access import require_any_permission, require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import (
    AuditEvent,
    Company,
    Demand,
    DemandCategory,
    DemandUpdate,
    Membership,
    MembershipStatus,
    UserProfile,
    Workflow,
    WorkflowStage,
    WorkflowVersion,
    utc_now,
)

router = APIRouter(prefix="/demands", tags=["Demandas"])


class DemandCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    company_id: uuid.UUID | None = Field(default=None, alias="companyId")
    category_id: uuid.UUID | None = Field(default=None, alias="categoryId")
    priority: str = Field(default="NORMAL", pattern=r"^(LOW|NORMAL|HIGH|URGENT)$")
    deadline_at: datetime | None = Field(default=None, alias="deadlineAt")
    assignee_id: uuid.UUID | None = Field(default=None, alias="assigneeId")
    stage_id: uuid.UUID | None = Field(default=None, alias="stageId")
    workflow_id: uuid.UUID | None = Field(default=None, alias="workflowId")


class DemandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    public_id: str = Field(alias="publicId")
    title: str
    description: str | None
    primary_company_id: uuid.UUID | None = Field(alias="primaryCompanyId")
    company_name: str | None = Field(alias="companyName")
    company_color: str | None = Field(alias="companyColor")
    category_id: uuid.UUID | None = Field(alias="categoryId")
    category_name: str | None = Field(alias="categoryName")
    category_color: str | None = Field(alias="categoryColor")
    assignee_id: uuid.UUID | None = Field(alias="assigneeId")
    assignee_name: str | None = Field(alias="assigneeName")
    assignee_avatar_url: str | None = Field(alias="assigneeAvatarUrl")
    created_by_id: uuid.UUID = Field(alias="createdById")
    created_by_name: str = Field(alias="createdByName")
    stage_id: uuid.UUID | None = Field(alias="stageId")
    stage_name: str | None = Field(alias="stageName")
    stage_code: str | None = Field(alias="stageCode")
    stage_color: str | None = Field(alias="stageColor")
    stage_position: int | None = Field(alias="stagePosition")
    workflow_id: uuid.UUID | None = Field(alias="workflowId")
    workflow_name: str | None = Field(alias="workflowName")
    workflow_version: int | None = Field(alias="workflowVersion")
    status: str
    priority: str
    deadline_at: datetime | None = Field(alias="deadlineAt")
    forecast_at: datetime | None = Field(alias="forecastAt")
    expected_effort_minutes: int | None = Field(alias="expectedEffortMinutes")
    revision: int
    created_at: datetime = Field(alias="createdAt")


class DemandEdit(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    company_id: uuid.UUID | None = Field(default=None, alias="companyId")
    category_id: uuid.UUID | None = Field(default=None, alias="categoryId")
    priority: str = Field(pattern=r"^(LOW|NORMAL|HIGH|URGENT)$")
    status: str = Field(
        pattern=r"^(WAITING_EXECUTION|IN_PROGRESS|WAITING_INFORMATION|WAITING_APPROVAL|BLOCKED|SCHEDULED|COMPLETED)$"
    )
    deadline_at: datetime | None = Field(default=None, alias="deadlineAt")
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    assignee_id: uuid.UUID | None = Field(default=None, alias="assigneeId")
    stage_id: uuid.UUID | None = Field(default=None, alias="stageId")
    workflow_id: uuid.UUID | None = Field(default=None, alias="workflowId")


class DemandStageUpdate(BaseModel):
    stage_id: uuid.UUID = Field(alias="stageId")
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class DemandUpdateOut(BaseModel):
    id: uuid.UUID
    kind: str
    summary: str
    payload: dict[str, object]
    created_at: datetime = Field(alias="createdAt")


class DemandTimelineStageOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    color: str
    position: int
    state: str
    entered_at: datetime | None = Field(alias="enteredAt")
    left_at: datetime | None = Field(alias="leftAt")
    forecast_at: datetime | None = Field(alias="forecastAt")
    expected_duration_hours: int | None = Field(alias="expectedDurationHours")
    assignee_id: uuid.UUID | None = Field(alias="assigneeId")
    assignee_name: str | None = Field(alias="assigneeName")


class DemandTimelineOut(BaseModel):
    workflow_id: uuid.UUID = Field(alias="workflowId")
    workflow_name: str = Field(alias="workflowName")
    version: int
    stages: list[DemandTimelineStageOut]


def workflow_definition(stages: list[WorkflowStage]) -> dict[str, Any]:
    return {
        "stages": [
            {
                "id": str(stage.id),
                "name": stage.name,
                "code": stage.code,
                "color": stage.color,
                "position": stage.position,
                "defaultAssigneeId": (
                    str(stage.default_assignee_id) if stage.default_assignee_id else None
                ),
                "expectedDurationHours": stage.expected_duration_hours,
            }
            for stage in sorted(stages, key=lambda item: (item.position, item.name))
            if stage.active
        ]
    }


def ensure_workflow_version(
    db: Session,
    organization_id: uuid.UUID,
    workflow_id: uuid.UUID,
    created_by: uuid.UUID,
) -> WorkflowVersion:
    db.scalar(
        select(Workflow.id)
        .where(Workflow.id == workflow_id, Workflow.organization_id == organization_id)
        .with_for_update()
    )
    stages = list(
        db.scalars(
            select(WorkflowStage).where(
                WorkflowStage.organization_id == organization_id,
                WorkflowStage.workflow_id == workflow_id,
            )
        )
    )
    definition = workflow_definition(stages)
    latest = db.scalar(
        select(WorkflowVersion)
        .where(
            WorkflowVersion.organization_id == organization_id,
            WorkflowVersion.workflow_id == workflow_id,
        )
        .order_by(WorkflowVersion.version.desc())
        .limit(1)
    )
    if latest and latest.definition == definition:
        return latest
    version = WorkflowVersion(
        organization_id=organization_id,
        workflow_id=workflow_id,
        version=(latest.version + 1) if latest else 1,
        definition=definition,
        created_by=created_by,
    )
    db.add(version)
    db.flush()
    return version


def version_stage(
    version: WorkflowVersion | None, stage_id: uuid.UUID | None
) -> dict[str, Any] | None:
    if version is None or stage_id is None:
        return None
    stages = version.definition.get("stages", [])
    if not isinstance(stages, list):
        return None
    return next(
        (
            item
            for item in stages
            if isinstance(item, dict) and item.get("id") == str(stage_id)
        ),
        None,
    )


def apply_stage_snapshot_defaults(
    demand: Demand,
    stage: dict[str, Any],
    *,
    apply_assignee: bool = True,
    entered_at: datetime | None = None,
) -> None:
    default_assignee_id = stage.get("defaultAssigneeId")
    if apply_assignee and default_assignee_id:
        demand.current_assignee_id = uuid.UUID(str(default_assignee_id))
    expected_duration = stage.get("expectedDurationHours")
    demand.forecast_at = (
        (entered_at or utc_now()) + timedelta(hours=int(expected_duration))
        if expected_duration
        else None
    )


def apply_stage_defaults(
    demand: Demand,
    stage: WorkflowStage,
    *,
    apply_assignee: bool = True,
    entered_at: datetime | None = None,
) -> None:
    if apply_assignee and stage.default_assignee_id:
        demand.current_assignee_id = stage.default_assignee_id
    demand.forecast_at = (
        (entered_at or utc_now()) + timedelta(hours=stage.expected_duration_hours)
        if stage.expected_duration_hours
        else None
    )


def next_public_id(db: Session) -> str:
    year = utc_now().year
    number = db.execute(
        text(
            "INSERT INTO app.demand_counters (year, last_value) VALUES (:year, 1) "
            "ON CONFLICT (year) DO UPDATE "
            "SET last_value = demand_counters.last_value + 1 "
            "RETURNING last_value"
        ),
        {"year": year},
    ).scalar_one()
    return f"DMD-{year}-{number:06d}"


def create_demand_record(
    db: Session,
    principal: Principal,
    *,
    title: str,
    description: str | None = None,
    company_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    priority: str = "NORMAL",
    deadline_at: datetime | None = None,
    assignee_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
    source: str = "interface",
) -> Demand:
    if workflow_id is None:
        workflow_id = db.scalar(
            select(Workflow.id).where(
                Workflow.organization_id == principal.membership.organization_id,
                Workflow.is_default.is_(True),
                Workflow.active.is_(True),
            )
        )
    if stage_id is None and workflow_id:
        stage_id = db.scalar(
            select(WorkflowStage.id)
            .where(
                WorkflowStage.organization_id == principal.membership.organization_id,
                WorkflowStage.workflow_id == workflow_id,
                WorkflowStage.active.is_(True),
            )
            .order_by(WorkflowStage.position)
            .limit(1)
        )
    if workflow_id is None:
        raise ApiError(422, "workflow_required", "Nenhum workflow ativo está disponível.")
    workflow_version = ensure_workflow_version(
        db,
        principal.membership.organization_id,
        workflow_id,
        principal.profile.id,
    )
    demand = Demand(
        organization_id=principal.membership.organization_id,
        public_id=next_public_id(db),
        title=" ".join(title.split()),
        description=description,
        primary_company_id=company_id,
        category_id=category_id,
        priority=priority,
        deadline_at=deadline_at,
        current_assignee_id=assignee_id,
        current_stage_id=stage_id,
        workflow_id=workflow_id,
        workflow_version_id=workflow_version.id,
        source=source,
        created_by=principal.profile.id,
    )
    stage_snapshot = version_stage(workflow_version, stage_id)
    if stage_snapshot:
        apply_stage_snapshot_defaults(
            demand,
            stage_snapshot,
            apply_assignee=assignee_id is None,
        )
    db.add(demand)
    db.flush()
    return demand


def demand_out(db: Session, demand: Demand) -> DemandOut:
    company = db.get(Company, demand.primary_company_id) if demand.primary_company_id else None
    category = db.get(DemandCategory, demand.category_id) if demand.category_id else None
    assignee = db.get(UserProfile, demand.current_assignee_id) if demand.current_assignee_id else None
    creator = db.get(UserProfile, demand.created_by)
    assert creator is not None
    stage = db.get(WorkflowStage, demand.current_stage_id) if demand.current_stage_id else None
    workflow = db.get(Workflow, demand.workflow_id) if demand.workflow_id else None
    version = db.get(WorkflowVersion, demand.workflow_version_id) if demand.workflow_version_id else None
    stage_snapshot = version_stage(version, demand.current_stage_id)
    return DemandOut(
        id=demand.id,
        publicId=demand.public_id,
        title=demand.title,
        description=demand.description,
        primaryCompanyId=demand.primary_company_id,
        companyName=company.name if company else None,
        companyColor=company.color if company else None,
        categoryId=demand.category_id,
        categoryName=category.name if category else None,
        categoryColor=category.color if category else None,
        assigneeId=demand.current_assignee_id,
        assigneeName=assignee.full_name if assignee else None,
        assigneeAvatarUrl=(
            f"/api/v1/users/{assignee.id}/avatar?v={assignee.revision}"
            if assignee and assignee.avatar_path
            else None
        ),
        createdById=creator.id,
        createdByName=creator.full_name,
        stageId=demand.current_stage_id,
        stageName=str(stage_snapshot["name"]) if stage_snapshot else stage.name if stage else None,
        stageCode=str(stage_snapshot["code"]) if stage_snapshot else stage.code if stage else None,
        stageColor=str(stage_snapshot["color"]) if stage_snapshot else stage.color if stage else None,
        stagePosition=(
            int(stage_snapshot["position"])
            if stage_snapshot
            else stage.position if stage else None
        ),
        workflowId=demand.workflow_id,
        workflowName=workflow.name if workflow else None,
        workflowVersion=version.version if version else None,
        status=demand.status,
        priority=demand.priority,
        deadlineAt=demand.deadline_at,
        forecastAt=demand.forecast_at,
        expectedEffortMinutes=demand.expected_effort_minutes,
        revision=demand.revision,
        createdAt=demand.created_at,
    )


def validate_references(
    db: Session,
    organization_id: uuid.UUID,
    *,
    company_id: uuid.UUID | None,
    category_id: uuid.UUID | None,
    assignee_id: uuid.UUID | None,
    stage_id: uuid.UUID | None,
    workflow_id: uuid.UUID | None,
) -> tuple[uuid.UUID, uuid.UUID | None]:
    if company_id and not db.scalar(
        select(Company.id).where(
            Company.id == company_id, Company.organization_id == organization_id, Company.active
        )
    ):
        raise ApiError(422, "company_invalid", "A empresa selecionada não está disponível.")
    if category_id and not db.scalar(
        select(DemandCategory.id).where(
            DemandCategory.id == category_id,
            DemandCategory.organization_id == organization_id,
            DemandCategory.active,
        )
    ):
        raise ApiError(422, "category_invalid", "A categoria selecionada não está disponível.")
    if assignee_id and not db.scalar(
        select(Membership.id).where(
            Membership.organization_id == organization_id,
            Membership.user_profile_id == assignee_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ):
        raise ApiError(422, "assignee_invalid", "O responsável selecionado não está disponível.")
    resolved_workflow_id = workflow_id
    stage: WorkflowStage | None = None
    if stage_id:
        stage = db.scalar(
            select(WorkflowStage).where(
                WorkflowStage.id == stage_id,
                WorkflowStage.organization_id == organization_id,
                WorkflowStage.active.is_(True),
            )
        )
        if not stage:
            raise ApiError(422, "stage_invalid", "A etapa selecionada não está disponível.")
        if resolved_workflow_id and stage.workflow_id != resolved_workflow_id:
            raise ApiError(422, "stage_workflow_mismatch", "A etapa não pertence ao workflow selecionado.")
        resolved_workflow_id = stage.workflow_id
    if resolved_workflow_id and not db.scalar(
        select(Workflow.id).where(
            Workflow.id == resolved_workflow_id,
            Workflow.organization_id == organization_id,
            Workflow.active.is_(True),
        )
    ):
        raise ApiError(422, "workflow_invalid", "O workflow selecionado não está disponível.")
    if not resolved_workflow_id and category_id:
        resolved_workflow_id = db.scalar(
            select(DemandCategory.default_workflow_id).where(
                DemandCategory.id == category_id,
                DemandCategory.organization_id == organization_id,
            )
        )
    if not resolved_workflow_id:
        resolved_workflow_id = db.scalar(
            select(Workflow.id).where(
                Workflow.organization_id == organization_id,
                Workflow.is_default.is_(True),
                Workflow.active.is_(True),
            )
        )
    if not resolved_workflow_id:
        raise ApiError(422, "workflow_required", "Nenhum workflow ativo está disponível.")
    resolved_stage_id = stage.id if stage else None
    if not resolved_stage_id:
        resolved_stage_id = db.scalar(
            select(WorkflowStage.id)
            .where(
                WorkflowStage.organization_id == organization_id,
                WorkflowStage.workflow_id == resolved_workflow_id,
                WorkflowStage.active.is_(True),
            )
            .order_by(WorkflowStage.position)
            .limit(1)
        )
    return resolved_workflow_id, resolved_stage_id


@router.get("", response_model=list[DemandOut])
def list_demands(
    q: str | None = Query(default=None, max_length=300),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[DemandOut]:
    require_permission(principal, "demands:read")
    statement = select(Demand).where(
        Demand.organization_id == principal.membership.organization_id,
        Demand.deleted_at.is_(None),
        Demand.archived_at.is_(None),
    )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(Demand.public_id.ilike(pattern), Demand.title.ilike(pattern))
        )
    demands = list(db.scalars(statement.order_by(Demand.updated_at.desc()).limit(50)))
    return [demand_out(db, demand) for demand in demands]


@router.post(
    "",
    response_model=DemandOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_demand(
    payload: DemandCreate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandOut:
    require_any_permission(principal, "demands:write", "demands:work")
    workflow_id, stage_id = validate_references(
        db,
        principal.membership.organization_id,
        company_id=payload.company_id,
        category_id=payload.category_id,
        assignee_id=payload.assignee_id,
        stage_id=payload.stage_id,
        workflow_id=payload.workflow_id,
    )
    stage = db.get(WorkflowStage, stage_id) if stage_id else None
    resolved_assignee_id = payload.assignee_id or (stage.default_assignee_id if stage else None)
    demand = create_demand_record(
        db,
        principal,
        title=payload.title,
        description=payload.description,
        company_id=payload.company_id,
        category_id=payload.category_id,
        priority=payload.priority,
        deadline_at=payload.deadline_at,
        assignee_id=resolved_assignee_id,
        stage_id=stage_id,
        workflow_id=workflow_id,
    )
    version = db.get(WorkflowVersion, demand.workflow_version_id)
    db.add(
        DemandUpdate(
            demand_id=demand.id,
            created_by=principal.profile.id,
            kind="DEMAND_CREATED",
            summary="Demanda criada.",
            payload={
                "publicId": demand.public_id,
                "source": demand.source,
                "workflowId": str(demand.workflow_id),
                "workflowVersion": version.version if version else None,
                "stageId": str(stage_id) if stage_id else None,
            },
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type="DEMAND_CREATED",
            metadata_json={"demandId": str(demand.id), "publicId": demand.public_id},
        )
    )
    db.commit()
    db.refresh(demand)
    return demand_out(db, demand)


@router.get("/{demand_id}", response_model=DemandOut)
def get_demand(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandOut:
    require_permission(principal, "demands:read")
    demand = db.scalar(
        select(Demand).where(
            Demand.id == demand_id,
            Demand.organization_id == principal.membership.organization_id,
            Demand.deleted_at.is_(None),
        )
    )
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    return demand_out(db, demand)


@router.put(
    "/{demand_id}",
    response_model=DemandOut,
    dependencies=[Depends(require_csrf)],
)
def update_demand(
    demand_id: uuid.UUID,
    payload: DemandEdit,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = db.scalar(
        select(Demand)
        .where(
            Demand.id == demand_id,
            Demand.organization_id == principal.membership.organization_id,
            Demand.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    if demand.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "A demanda foi alterada. Atualize a tela.")
    current_version = (
        db.get(WorkflowVersion, demand.workflow_version_id)
        if demand.workflow_version_id
        else None
    )
    keep_version = (
        payload.workflow_id == demand.workflow_id
        and version_stage(current_version, payload.stage_id) is not None
    )
    if keep_version:
        workflow_id, _ = validate_references(
            db,
            principal.membership.organization_id,
            company_id=payload.company_id,
            category_id=payload.category_id,
            assignee_id=payload.assignee_id,
            stage_id=None,
            workflow_id=demand.workflow_id,
        )
        stage_id = payload.stage_id
        target_version = current_version
    else:
        workflow_id, stage_id = validate_references(
            db,
            principal.membership.organization_id,
            company_id=payload.company_id,
            category_id=payload.category_id,
            assignee_id=payload.assignee_id,
            stage_id=payload.stage_id,
            workflow_id=payload.workflow_id,
        )
        target_version = ensure_workflow_version(
            db,
            principal.membership.organization_id,
            workflow_id,
            principal.profile.id,
        )
    before = {
        "title": demand.title,
        "status": demand.status,
        "priority": demand.priority,
        "stageId": str(demand.current_stage_id) if demand.current_stage_id else None,
        "workflowId": str(demand.workflow_id) if demand.workflow_id else None,
        "revision": demand.revision,
    }
    demand.title = " ".join(payload.title.split())
    demand.description = payload.description
    demand.primary_company_id = payload.company_id
    demand.category_id = payload.category_id
    demand.priority = payload.priority
    demand.status = payload.status
    demand.deadline_at = payload.deadline_at
    previous_stage_id = demand.current_stage_id
    target_stage = db.get(WorkflowStage, stage_id) if stage_id else None
    target_stage_snapshot = version_stage(target_version, stage_id)
    demand.current_assignee_id = payload.assignee_id
    demand.current_stage_id = stage_id
    demand.workflow_id = workflow_id
    if target_version:
        demand.workflow_version_id = target_version.id
    if target_stage_snapshot and previous_stage_id != stage_id:
        apply_stage_snapshot_defaults(
            demand,
            target_stage_snapshot,
            apply_assignee=payload.assignee_id is None,
        )
    elif target_stage and previous_stage_id != stage_id:
        apply_stage_defaults(demand, target_stage, apply_assignee=payload.assignee_id is None)
    demand.revision += 1
    demand.updated_at = utc_now()
    db.add(
        DemandUpdate(
            demand_id=demand.id,
            created_by=principal.profile.id,
            kind="DEMAND_UPDATED",
            summary=(
                f"Dados atualizados e etapa alterada para {target_stage_snapshot['name']}."
                if target_stage_snapshot and previous_stage_id != stage_id
                else f"Dados atualizados e etapa alterada para {target_stage.name}."
                if target_stage and previous_stage_id != stage_id
                else "Dados gerais da demanda atualizados."
            ),
            payload={
                "before": before,
                "after": {
                    "title": demand.title,
                    "status": demand.status,
                    "priority": demand.priority,
                    "stageId": str(stage_id) if stage_id else None,
                    "workflowId": str(workflow_id),
                    "workflowVersion": target_version.version if target_version else None,
                    "revision": demand.revision,
                },
            },
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type="DEMAND_UPDATED",
            metadata_json={
                "demandId": str(demand.id),
                "before": before,
                "after": {
                    "title": demand.title,
                    "status": demand.status,
                    "priority": demand.priority,
                    "revision": demand.revision,
                },
            },
        )
    )
    db.commit()
    db.refresh(demand)
    return demand_out(db, demand)


@router.patch(
    "/{demand_id}/stage",
    response_model=DemandOut,
    dependencies=[Depends(require_csrf)],
)
def move_demand_stage(
    demand_id: uuid.UUID,
    payload: DemandStageUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = db.scalar(
        select(Demand)
        .where(
            Demand.id == demand_id,
            Demand.organization_id == principal.membership.organization_id,
            Demand.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    if demand.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "A demanda foi alterada. Atualize a tela.")
    version = (
        db.get(WorkflowVersion, demand.workflow_version_id)
        if demand.workflow_version_id
        else None
    )
    stage_snapshot = version_stage(version, payload.stage_id)
    stage = db.get(WorkflowStage, payload.stage_id)
    if (
        not stage_snapshot
        or not stage
        or stage.organization_id != principal.membership.organization_id
        or stage.workflow_id != demand.workflow_id
    ):
        raise ApiError(422, "stage_invalid", "A etapa selecionada não está disponível.")
    previous_stage_id = demand.current_stage_id
    demand.current_stage_id = stage.id
    apply_stage_snapshot_defaults(demand, stage_snapshot)
    demand.revision += 1
    demand.updated_at = utc_now()
    db.add(
        DemandUpdate(
            demand_id=demand.id,
            created_by=principal.profile.id,
            kind="STAGE_CHANGED",
            summary=f"Etapa alterada para {stage_snapshot['name']}.",
            payload={
                "fromStageId": str(previous_stage_id) if previous_stage_id else None,
                "toStageId": str(stage.id),
                "toStageName": str(stage_snapshot["name"]),
                "assigneeId": (
                    str(demand.current_assignee_id) if demand.current_assignee_id else None
                ),
                "forecastAt": demand.forecast_at.isoformat() if demand.forecast_at else None,
            },
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type="DEMAND_STAGE_CHANGED",
            metadata_json={
                "demandId": str(demand.id),
                "fromStageId": str(previous_stage_id) if previous_stage_id else None,
                "toStageId": str(stage.id),
                "assigneeId": (
                    str(demand.current_assignee_id) if demand.current_assignee_id else None
                ),
                "forecastAt": demand.forecast_at.isoformat() if demand.forecast_at else None,
            },
        )
    )
    db.commit()
    db.refresh(demand)
    return demand_out(db, demand)


@router.get("/{demand_id}/timeline", response_model=DemandTimelineOut)
def get_demand_timeline(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandTimelineOut:
    require_permission(principal, "demands:read")
    demand = db.scalar(
        select(Demand).where(
            Demand.id == demand_id,
            Demand.organization_id == principal.membership.organization_id,
            Demand.deleted_at.is_(None),
        )
    )
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    version = (
        db.get(WorkflowVersion, demand.workflow_version_id)
        if demand.workflow_version_id
        else None
    )
    workflow = db.get(Workflow, demand.workflow_id) if demand.workflow_id else None
    if not version or not workflow:
        raise ApiError(409, "workflow_version_missing", "O fluxo desta demanda precisa ser revisado.")

    raw_stages = version.definition.get("stages", [])
    stages = [item for item in raw_stages if isinstance(item, dict)]
    updates = list(
        db.scalars(
            select(DemandUpdate)
            .where(DemandUpdate.demand_id == demand.id)
            .order_by(DemandUpdate.created_at)
        )
    )
    entered_at: dict[str, datetime] = {}
    left_at: dict[str, datetime] = {}
    visited: set[str] = set()
    for update in updates:
        from_stage_id: object | None = None
        to_stage_id: object | None = None
        if update.kind == "DEMAND_CREATED":
            to_stage_id = update.payload.get("stageId")
        elif update.kind == "STAGE_CHANGED":
            from_stage_id = update.payload.get("fromStageId")
            to_stage_id = update.payload.get("toStageId")
        elif update.kind == "DEMAND_UPDATED":
            before = update.payload.get("before", {})
            after = update.payload.get("after", {})
            if isinstance(before, dict) and isinstance(after, dict):
                previous = before.get("stageId")
                current = after.get("stageId")
                if previous != current:
                    from_stage_id = previous
                    to_stage_id = current
        if from_stage_id:
            left_at[str(from_stage_id)] = update.created_at
            visited.add(str(from_stage_id))
        if to_stage_id:
            entered_at[str(to_stage_id)] = update.created_at
            visited.add(str(to_stage_id))

    current_stage_id = str(demand.current_stage_id) if demand.current_stage_id else None
    if current_stage_id:
        visited.add(current_stage_id)
        entered_at.setdefault(current_stage_id, demand.created_at)
    current_position = next(
        (
            int(item.get("position", 0))
            for item in stages
            if item.get("id") == current_stage_id
        ),
        0,
    )
    forecast_cursor = demand.forecast_at or utc_now()
    timeline: list[DemandTimelineStageOut] = []
    for item in sorted(stages, key=lambda value: int(value.get("position", 0))):
        item_id = str(item.get("id"))
        position = int(item.get("position", 0))
        if item_id == current_stage_id:
            state = "current"
            stage_forecast = demand.forecast_at
        elif item_id in left_at:
            state = "completed"
            stage_forecast = None
        elif position < current_position:
            state = "skipped"
            stage_forecast = None
        else:
            state = "upcoming"
            expected_duration = item.get("expectedDurationHours")
            if expected_duration:
                forecast_cursor += timedelta(hours=int(expected_duration))
                stage_forecast = forecast_cursor
            else:
                stage_forecast = None
        assignee_id_value = item.get("defaultAssigneeId")
        assignee_id = uuid.UUID(str(assignee_id_value)) if assignee_id_value else None
        if item_id == current_stage_id and demand.current_assignee_id:
            assignee_id = demand.current_assignee_id
        assignee = db.get(UserProfile, assignee_id) if assignee_id else None
        timeline.append(
            DemandTimelineStageOut(
                id=uuid.UUID(item_id),
                name=str(item.get("name", "Etapa")),
                code=str(item.get("code", "ETAPA")),
                color=str(item.get("color", "#94A3B8")),
                position=position,
                state=state,
                enteredAt=entered_at.get(item_id),
                leftAt=left_at.get(item_id),
                forecastAt=stage_forecast,
                expectedDurationHours=(
                    int(item["expectedDurationHours"])
                    if item.get("expectedDurationHours")
                    else None
                ),
                assigneeId=assignee_id,
                assigneeName=assignee.full_name if assignee else None,
            )
        )
    return DemandTimelineOut(
        workflowId=workflow.id,
        workflowName=workflow.name,
        version=version.version,
        stages=timeline,
    )


@router.get("/{demand_id}/updates", response_model=list[DemandUpdateOut])
def list_demand_updates(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[DemandUpdateOut]:
    require_permission(principal, "demands:read")
    demand = db.scalar(
        select(Demand).where(
            Demand.id == demand_id,
            Demand.organization_id == principal.membership.organization_id,
            Demand.deleted_at.is_(None),
        )
    )
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    updates = db.scalars(
        select(DemandUpdate)
        .where(DemandUpdate.demand_id == demand.id)
        .order_by(DemandUpdate.created_at.desc())
    )
    return [
        DemandUpdateOut(
            id=update.id,
            kind=update.kind,
            summary=update.summary,
            payload=update.payload,
            createdAt=update.created_at,
        )
        for update in updates
    ]
