import re
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.access import require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import (
    AuditEvent,
    Company,
    Demand,
    DemandCategory,
    JobRole,
    Membership,
    MembershipStatus,
    Workflow,
    WorkflowStage,
    utc_now,
)

router = APIRouter(prefix="/catalogs", tags=["Cadastros"])


class CompanyInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    short_name: str = Field(alias="shortName", min_length=1, max_length=80)
    code: str = Field(min_length=2, max_length=40)
    color: str = Field(default="#155E75", pattern=r"^#[0-9A-Fa-f]{6}$")
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "short_name")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("code")
    @classmethod
    def clean_code(cls, value: str) -> str:
        normalized = re.sub(r"[^A-Z0-9_]+", "_", value.upper()).strip("_")
        if len(normalized) < 2:
            raise ValueError("Código inválido")
        return normalized


class CompanyUpdate(CompanyInput):
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    active: bool = True


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    name: str
    short_name: str = Field(alias="shortName")
    code: str
    color: str
    description: str | None
    active: bool
    revision: int


class CategoryInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=50)
    color: str = Field(default="#475569", pattern=r"^#[0-9A-Fa-f]{6}$")
    default_workflow_id: uuid.UUID | None = Field(default=None, alias="defaultWorkflowId")

    @field_validator("code")
    @classmethod
    def clean_category_code(cls, value: str) -> str:
        normalized = re.sub(r"[^A-Z0-9_]+", "_", value.upper()).strip("_")
        if len(normalized) < 2:
            raise ValueError("Código inválido")
        return normalized


class CategoryUpdate(CategoryInput):
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    active: bool = True


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    name: str
    code: str
    color: str
    default_workflow_id: uuid.UUID | None = Field(alias="defaultWorkflowId")
    active: bool
    revision: int


class JobRoleInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class JobRoleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    active: bool
    revision: int


class WorkflowStageInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=50)
    color: str = Field(default="#475569", pattern=r"^#[0-9A-Fa-f]{6}$")
    position: int = Field(ge=1, le=100)
    default_assignee_id: uuid.UUID | None = Field(default=None, alias="defaultAssigneeId")
    expected_duration_hours: int | None = Field(
        default=None, alias="expectedDurationHours", ge=1, le=8760
    )
    workflow_id: uuid.UUID | None = Field(default=None, alias="workflowId")

    @field_validator("name")
    @classmethod
    def clean_stage_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("code")
    @classmethod
    def clean_stage_code(cls, value: str) -> str:
        normalized = re.sub(r"[^A-Z0-9_]+", "_", value.upper()).strip("_")
        if len(normalized) < 2:
            raise ValueError("Código inválido")
        return normalized


class WorkflowStageUpdate(WorkflowStageInput):
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    active: bool = True


class WorkflowStageOrderItem(BaseModel):
    id: uuid.UUID
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class WorkflowStageReorder(BaseModel):
    stages: list[WorkflowStageOrderItem] = Field(min_length=1, max_length=50)


class WorkflowStageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    workflow_id: uuid.UUID | None = Field(alias="workflowId")
    name: str
    code: str
    color: str
    position: int
    default_assignee_id: uuid.UUID | None = Field(alias="defaultAssigneeId")
    expected_duration_hours: int | None = Field(alias="expectedDurationHours")
    active: bool
    revision: int


class WorkflowInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    is_default: bool = Field(default=False, alias="isDefault")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("code")
    @classmethod
    def clean_workflow_code(cls, value: str) -> str:
        normalized = re.sub(r"[^A-Z0-9_]+", "_", value.upper()).strip("_")
        if len(normalized) < 2:
            raise ValueError("Código inválido")
        return normalized


class WorkflowUpdate(WorkflowInput):
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    active: bool = True


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    name: str
    code: str
    description: str | None
    is_default: bool = Field(alias="isDefault")
    active: bool
    revision: int


def _validate_stage_default_assignee(
    db: Session, organization_id: uuid.UUID, assignee_id: uuid.UUID | None
) -> None:
    if assignee_id is None:
        return
    if not db.scalar(
        select(Membership.id).where(
            Membership.organization_id == organization_id,
            Membership.user_profile_id == assignee_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ):
        raise ApiError(
            422,
            "default_assignee_invalid",
            "O responsável padrão precisa ser um integrante ativo da equipe.",
        )


def _validate_workflow(
    db: Session, organization_id: uuid.UUID, workflow_id: uuid.UUID | None
) -> Workflow | None:
    if workflow_id is None:
        return None
    workflow = db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.organization_id == organization_id,
            Workflow.active.is_(True),
        )
    )
    if not workflow:
        raise ApiError(422, "workflow_invalid", "O workflow selecionado não está disponível.")
    return workflow


def _audit(
    db: Session,
    principal: Principal,
    event_type: str,
    entity_id: uuid.UUID,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type=event_type,
            metadata_json={
                "entityId": str(entity_id),
                "before": before or {},
                "after": after or {},
            },
        )
    )


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(
    include_inactive: bool = Query(False, alias="includeInactive"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[Company]:
    require_permission(principal, "catalog:read")
    statement = select(Company).where(
        Company.organization_id == principal.membership.organization_id
    )
    if not include_inactive:
        statement = statement.where(Company.active.is_(True))
    return list(db.scalars(statement.order_by(Company.name)))


@router.post(
    "/companies",
    response_model=CompanyOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_company(
    payload: CompanyInput,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Company:
    require_permission(principal, "catalog:write")
    company = Company(
        organization_id=principal.membership.organization_id,
        name=payload.name,
        short_name=payload.short_name,
        code=payload.code,
        color=payload.color.upper(),
        description=payload.description,
    )
    db.add(company)
    try:
        db.flush()
        _audit(db, principal, "COMPANY_CREATED", company.id, after={"name": company.name})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "company_conflict", "Nome ou código já utilizado.") from exc
    db.refresh(company)
    return company


@router.put(
    "/companies/{company_id}",
    response_model=CompanyOut,
    dependencies=[Depends(require_csrf)],
)
def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Company:
    require_permission(principal, "catalog:write")
    company = db.scalar(
        select(Company)
        .where(
            Company.id == company_id,
            Company.organization_id == principal.membership.organization_id,
        )
        .with_for_update()
    )
    if not company:
        raise ApiError(404, "company_not_found", "Empresa não encontrada.")
    if company.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "A empresa foi alterada. Atualize a tela.")
    before = {"name": company.name, "code": company.code, "revision": company.revision}
    for field, value in payload.model_dump(by_alias=False, exclude={"expected_revision"}).items():
        setattr(company, field, value.upper() if field == "color" else value)
    company.revision += 1
    company.updated_at = utc_now()
    _audit(
        db,
        principal,
        "COMPANY_UPDATED",
        company.id,
        before=before,
        after={"name": company.name, "code": company.code, "revision": company.revision},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "company_conflict", "Nome ou código já utilizado.") from exc
    db.refresh(company)
    return company


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> list[DemandCategory]:
    require_permission(principal, "catalog:read")
    return list(
        db.scalars(
            select(DemandCategory)
            .where(
                DemandCategory.organization_id == principal.membership.organization_id,
                DemandCategory.active.is_(True),
            )
            .order_by(DemandCategory.name)
        )
    )


@router.post(
    "/categories",
    response_model=CategoryOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_category(
    payload: CategoryInput,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandCategory:
    require_permission(principal, "catalog:write")
    _validate_workflow(db, principal.membership.organization_id, payload.default_workflow_id)
    category = DemandCategory(
        organization_id=principal.membership.organization_id,
        name=payload.name,
        code=payload.code,
        color=payload.color.upper(),
        default_workflow_id=payload.default_workflow_id,
    )
    db.add(category)
    try:
        db.flush()
        _audit(db, principal, "CATEGORY_CREATED", category.id, after={"name": category.name})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "category_conflict", "Nome ou código já utilizado.") from exc
    db.refresh(category)
    return category


@router.put(
    "/categories/{category_id}",
    response_model=CategoryOut,
    dependencies=[Depends(require_csrf)],
)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandCategory:
    require_permission(principal, "catalog:write")
    category = db.scalar(
        select(DemandCategory)
        .where(
            DemandCategory.id == category_id,
            DemandCategory.organization_id == principal.membership.organization_id,
        )
        .with_for_update()
    )
    if not category:
        raise ApiError(404, "category_not_found", "Categoria não encontrada.")
    if category.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "A categoria foi alterada. Atualize a tela.")
    _validate_workflow(db, principal.membership.organization_id, payload.default_workflow_id)
    before = {"name": category.name, "code": category.code, "revision": category.revision}
    category.name = payload.name
    category.code = payload.code
    category.color = payload.color.upper()
    category.default_workflow_id = payload.default_workflow_id
    category.active = payload.active
    category.revision += 1
    _audit(
        db,
        principal,
        "CATEGORY_UPDATED",
        category.id,
        before=before,
        after={
            "name": category.name,
            "code": category.code,
            "revision": category.revision,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "category_conflict", "Nome ou código já utilizado.") from exc
    db.refresh(category)
    return category


@router.get("/workflows", response_model=list[WorkflowOut])
def list_workflows(
    include_inactive: bool = Query(False, alias="includeInactive"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[Workflow]:
    require_permission(principal, "catalog:read")
    statement = select(Workflow).where(
        Workflow.organization_id == principal.membership.organization_id
    )
    if not include_inactive:
        statement = statement.where(Workflow.active.is_(True))
    return list(db.scalars(statement.order_by(Workflow.is_default.desc(), Workflow.name)))


@router.post(
    "/workflows",
    response_model=WorkflowOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_workflow(
    payload: WorkflowInput,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Workflow:
    require_permission(principal, "catalog:write")
    organization_id = principal.membership.organization_id
    has_default = db.scalar(
        select(Workflow.id).where(
            Workflow.organization_id == organization_id,
            Workflow.is_default.is_(True),
            Workflow.active.is_(True),
        )
    )
    make_default = payload.is_default or not has_default
    if make_default and has_default:
        for current in db.scalars(
            select(Workflow).where(
                Workflow.organization_id == organization_id,
                Workflow.is_default.is_(True),
            )
        ):
            current.is_default = False
            current.revision += 1
            current.updated_at = utc_now()
        db.flush()
    workflow = Workflow(
        organization_id=organization_id,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        is_default=make_default,
    )
    db.add(workflow)
    try:
        db.flush()
        _audit(db, principal, "WORKFLOW_CREATED", workflow.id, after={"name": workflow.name})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "workflow_conflict", "Nome ou código de workflow já utilizado.") from exc
    db.refresh(workflow)
    return workflow


@router.put(
    "/workflows/{workflow_id}",
    response_model=WorkflowOut,
    dependencies=[Depends(require_csrf)],
)
def update_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Workflow:
    require_permission(principal, "catalog:write")
    organization_id = principal.membership.organization_id
    workflow = db.scalar(
        select(Workflow)
        .where(Workflow.id == workflow_id, Workflow.organization_id == organization_id)
        .with_for_update()
    )
    if not workflow:
        raise ApiError(404, "workflow_not_found", "Workflow não encontrado.")
    if workflow.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O workflow foi alterado. Atualize a tela.")
    if workflow.is_default and (not payload.is_default or not payload.active):
        raise ApiError(409, "default_workflow_required", "Defina outro workflow padrão antes de alterar este.")
    if not payload.active:
        in_use = db.scalar(
            select(Demand.id)
            .where(
                Demand.organization_id == organization_id,
                Demand.workflow_id == workflow.id,
                Demand.deleted_at.is_(None),
            )
            .limit(1)
        )
        if in_use:
            raise ApiError(409, "workflow_in_use", "Mude o workflow das demandas antes de desativá-lo.")
    if payload.is_default and not workflow.is_default:
        for current in db.scalars(
            select(Workflow).where(
                Workflow.organization_id == organization_id,
                Workflow.is_default.is_(True),
                Workflow.id != workflow.id,
            )
        ):
            current.is_default = False
            current.revision += 1
            current.updated_at = utc_now()
        db.flush()
    workflow.name = payload.name
    workflow.code = payload.code
    workflow.description = payload.description
    workflow.is_default = payload.is_default
    workflow.active = payload.active
    workflow.revision += 1
    workflow.updated_at = utc_now()
    _audit(db, principal, "WORKFLOW_UPDATED", workflow.id, after={"name": workflow.name, "revision": workflow.revision})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "workflow_conflict", "Nome ou código de workflow já utilizado.") from exc
    db.refresh(workflow)
    return workflow


@router.get("/workflow-stages", response_model=list[WorkflowStageOut])
def list_workflow_stages(
    include_inactive: bool = Query(False, alias="includeInactive"),
    workflow_id: uuid.UUID | None = Query(default=None, alias="workflowId"),
    all_workflows: bool = Query(False, alias="allWorkflows"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[WorkflowStage]:
    require_permission(principal, "catalog:read")
    statement = select(WorkflowStage).where(
        WorkflowStage.organization_id == principal.membership.organization_id
    )
    if workflow_id:
        statement = statement.where(WorkflowStage.workflow_id == workflow_id)
    elif not all_workflows:
        default_workflow_id = db.scalar(
            select(Workflow.id).where(
                Workflow.organization_id == principal.membership.organization_id,
                Workflow.is_default.is_(True),
                Workflow.active.is_(True),
            )
        )
        statement = statement.where(WorkflowStage.workflow_id == default_workflow_id)
    if not include_inactive:
        statement = statement.where(WorkflowStage.active.is_(True))
    return list(db.scalars(statement.order_by(WorkflowStage.position, WorkflowStage.name)))


@router.post(
    "/workflow-stages",
    response_model=WorkflowStageOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_workflow_stage(
    payload: WorkflowStageInput,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> WorkflowStage:
    require_permission(principal, "catalog:write")
    _validate_stage_default_assignee(
        db, principal.membership.organization_id, payload.default_assignee_id
    )
    workflow = _validate_workflow(
        db, principal.membership.organization_id, payload.workflow_id
    )
    if workflow is None:
        workflow = db.scalar(
            select(Workflow).where(
                Workflow.organization_id == principal.membership.organization_id,
                Workflow.is_default.is_(True),
                Workflow.active.is_(True),
            )
        )
    if workflow is None:
        raise ApiError(422, "workflow_required", "Crie um workflow antes de adicionar etapas.")
    stage = WorkflowStage(
        organization_id=principal.membership.organization_id,
        workflow_id=workflow.id,
        name=payload.name,
        code=payload.code,
        color=payload.color.upper(),
        position=payload.position,
        default_assignee_id=payload.default_assignee_id,
        expected_duration_hours=payload.expected_duration_hours,
    )
    db.add(stage)
    try:
        db.flush()
        _audit(db, principal, "WORKFLOW_STAGE_CREATED", stage.id, after={"name": stage.name})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "workflow_stage_conflict", "Este código de etapa já existe.") from exc
    db.refresh(stage)
    return stage


@router.put(
    "/workflow-stages/{stage_id}",
    response_model=WorkflowStageOut,
    dependencies=[Depends(require_csrf)],
)
def update_workflow_stage(
    stage_id: uuid.UUID,
    payload: WorkflowStageUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> WorkflowStage:
    require_permission(principal, "catalog:write")
    stage = db.scalar(
        select(WorkflowStage)
        .where(
            WorkflowStage.id == stage_id,
            WorkflowStage.organization_id == principal.membership.organization_id,
        )
        .with_for_update()
    )
    if not stage:
        raise ApiError(404, "workflow_stage_not_found", "Etapa não encontrada.")
    if stage.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "A etapa foi alterada. Atualize a tela.")
    _validate_stage_default_assignee(
        db, principal.membership.organization_id, payload.default_assignee_id
    )
    if payload.workflow_id and payload.workflow_id != stage.workflow_id:
        raise ApiError(422, "stage_workflow_immutable", "A etapa não pode ser movida para outro workflow.")
    if stage.active and not payload.active:
        demand_id = db.scalar(
            select(Demand.id)
            .where(
                Demand.organization_id == principal.membership.organization_id,
                Demand.current_stage_id == stage.id,
                Demand.deleted_at.is_(None),
            )
            .limit(1)
        )
        if demand_id:
            raise ApiError(
                409,
                "workflow_stage_in_use",
                "Mova as demandas desta etapa antes de desativá-la.",
            )
        another_active_stage = db.scalar(
            select(WorkflowStage.id)
            .where(
                WorkflowStage.organization_id == principal.membership.organization_id,
                WorkflowStage.workflow_id == stage.workflow_id,
                WorkflowStage.active.is_(True),
                WorkflowStage.id != stage.id,
            )
            .limit(1)
        )
        if not another_active_stage:
            raise ApiError(
                409,
                "workflow_requires_active_stage",
                "O workflow precisa manter ao menos uma etapa ativa.",
            )
    before = {
        "name": stage.name,
        "position": stage.position,
        "defaultAssigneeId": str(stage.default_assignee_id) if stage.default_assignee_id else None,
        "expectedDurationHours": stage.expected_duration_hours,
        "revision": stage.revision,
    }
    stage.name = payload.name
    stage.code = payload.code
    stage.color = payload.color.upper()
    stage.position = payload.position
    stage.default_assignee_id = payload.default_assignee_id
    stage.expected_duration_hours = payload.expected_duration_hours
    stage.active = payload.active
    stage.revision += 1
    stage.updated_at = utc_now()
    _audit(
        db,
        principal,
        "WORKFLOW_STAGE_UPDATED",
        stage.id,
        before=before,
        after={
            "name": stage.name,
            "position": stage.position,
            "defaultAssigneeId": (
                str(stage.default_assignee_id) if stage.default_assignee_id else None
            ),
            "expectedDurationHours": stage.expected_duration_hours,
            "revision": stage.revision,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "workflow_stage_conflict", "Este código de etapa já existe.") from exc
    db.refresh(stage)
    return stage


@router.patch(
    "/workflow-stages/order",
    response_model=list[WorkflowStageOut],
    dependencies=[Depends(require_csrf)],
)
def reorder_workflow_stages(
    payload: WorkflowStageReorder,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[WorkflowStage]:
    require_permission(principal, "catalog:write")
    organization_id = principal.membership.organization_id
    requested_stage_ids = [item.id for item in payload.stages]
    workflow_id = db.scalar(
        select(WorkflowStage.workflow_id).where(
            WorkflowStage.organization_id == organization_id,
            WorkflowStage.id == requested_stage_ids[0],
        )
    )
    stages = list(
        db.scalars(
            select(WorkflowStage)
            .where(
                WorkflowStage.organization_id == organization_id,
                WorkflowStage.workflow_id == workflow_id,
                WorkflowStage.active.is_(True),
            )
            .with_for_update()
        )
    )
    by_id = {stage.id: stage for stage in stages}
    requested_ids = requested_stage_ids
    if len(set(requested_ids)) != len(requested_ids) or set(requested_ids) != set(by_id):
        raise ApiError(
            422,
            "workflow_order_invalid",
            "A ordenação deve conter todas as etapas ativas uma única vez.",
        )
    before = [str(stage.id) for stage in sorted(stages, key=lambda item: item.position)]
    for position, item in enumerate(payload.stages, start=1):
        stage = by_id[item.id]
        if stage.revision != item.expected_revision:
            raise ApiError(409, "revision_conflict", "Uma etapa foi alterada. Atualize a tela.")
        stage.position = position
        stage.revision += 1
        stage.updated_at = utc_now()
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=principal.profile.id,
            event_type="WORKFLOW_STAGES_REORDERED",
            metadata_json={"before": before, "after": [str(value) for value in requested_ids]},
        )
    )
    db.commit()
    return sorted(stages, key=lambda item: item.position)


@router.get("/job-roles", response_model=list[JobRoleOut])
def list_job_roles(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> list[JobRole]:
    require_permission(principal, "catalog:read")
    return list(
        db.scalars(
            select(JobRole)
            .where(
                JobRole.organization_id == principal.membership.organization_id,
                JobRole.active.is_(True),
            )
            .order_by(JobRole.name)
        )
    )


@router.post(
    "/job-roles",
    response_model=JobRoleOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_job_role(
    payload: JobRoleInput,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> JobRole:
    require_permission(principal, "catalog:write")
    role = JobRole(
        organization_id=principal.membership.organization_id,
        name=" ".join(payload.name.split()),
        description=payload.description,
    )
    db.add(role)
    try:
        db.flush()
        _audit(db, principal, "JOB_ROLE_CREATED", role.id, after={"name": role.name})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "job_role_conflict", "Este cargo já foi cadastrado.") from exc
    db.refresh(role)
    return role
