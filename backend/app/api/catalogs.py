import re
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.access import require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import AuditEvent, Company, DemandCategory, JobRole, WorkflowStage, utc_now

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
    id: uuid.UUID
    name: str
    code: str
    color: str
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


class WorkflowStageOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    color: str
    position: int
    active: bool
    revision: int


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
    category = DemandCategory(
        organization_id=principal.membership.organization_id,
        name=payload.name,
        code=payload.code,
        color=payload.color.upper(),
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
    before = {"name": category.name, "code": category.code, "revision": category.revision}
    category.name = payload.name
    category.code = payload.code
    category.color = payload.color.upper()
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


@router.get("/workflow-stages", response_model=list[WorkflowStageOut])
def list_workflow_stages(
    include_inactive: bool = Query(False, alias="includeInactive"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[WorkflowStage]:
    require_permission(principal, "catalog:read")
    statement = select(WorkflowStage).where(
        WorkflowStage.organization_id == principal.membership.organization_id
    )
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
    stage = WorkflowStage(
        organization_id=principal.membership.organization_id,
        name=payload.name,
        code=payload.code,
        color=payload.color.upper(),
        position=payload.position,
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
    before = {"name": stage.name, "position": stage.position, "revision": stage.revision}
    stage.name = payload.name
    stage.code = payload.code
    stage.color = payload.color.upper()
    stage.position = payload.position
    stage.active = payload.active
    stage.revision += 1
    stage.updated_at = utc_now()
    _audit(
        db,
        principal,
        "WORKFLOW_STAGE_UPDATED",
        stage.id,
        before=before,
        after={"name": stage.name, "position": stage.position, "revision": stage.revision},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "workflow_stage_conflict", "Este código de etapa já existe.") from exc
    db.refresh(stage)
    return stage


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
