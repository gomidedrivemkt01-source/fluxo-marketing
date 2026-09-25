import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.access import require_any_permission, require_permission
from app.api.demands import DemandOut, demand_out
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import (
    AuditEvent,
    BriefingField,
    ChecklistTemplateItem,
    Demand,
    DemandBriefingAnswer,
    DemandCategory,
    DemandChecklistItem,
    DemandUpdate,
    UserProfile,
    WorkflowStage,
    utc_now,
)

catalog_router = APIRouter(prefix="/catalogs", tags=["Modelos de trabalho"])
demand_router = APIRouter(prefix="/demands", tags=["Conteúdo das demandas"])


def _clean_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    if len(normalized) < 2:
        raise ValueError("Chave inválida")
    return normalized


class BriefingFieldInput(BaseModel):
    label: str = Field(min_length=2, max_length=160)
    key: str = Field(min_length=2, max_length=80)
    help_text: str | None = Field(default=None, alias="helpText", max_length=1000)
    field_type: str = Field(
        default="text", alias="fieldType", pattern=r"^(text|long_text|number|date|select)$"
    )
    options: list[str] = Field(default_factory=list, max_length=50)
    required: bool = False
    position: int = Field(ge=1, le=200)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("key")
    @classmethod
    def clean_key(cls, value: str) -> str:
        return _clean_key(value)

    @field_validator("options")
    @classmethod
    def clean_options(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class BriefingFieldUpdate(BriefingFieldInput):
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    active: bool = True


class BriefingFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    label: str
    key: str
    help_text: str | None = Field(alias="helpText")
    field_type: str = Field(alias="fieldType")
    options: list[str]
    required: bool
    position: int
    active: bool
    revision: int


class ChecklistTemplateInput(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    description: str | None = Field(default=None, max_length=1000)
    position: int = Field(ge=1, le=200)
    required: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return " ".join(value.split())


class ChecklistTemplateUpdate(ChecklistTemplateInput):
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    active: bool = True


class ChecklistTemplateOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    position: int
    required: bool
    active: bool
    revision: int


class BriefingAnswerInput(BaseModel):
    field_id: uuid.UUID = Field(alias="fieldId")
    value: str | None = Field(default=None, max_length=10000)


class DemandBriefingInput(BaseModel):
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    answers: list[BriefingAnswerInput] = Field(max_length=200)


class DemandBriefingFieldOut(BriefingFieldOut):
    value: str | None


class DemandBriefingOut(BaseModel):
    category_id: uuid.UUID | None = Field(alias="categoryId")
    category_name: str | None = Field(alias="categoryName")
    fields: list[DemandBriefingFieldOut]


class ChecklistToggleInput(BaseModel):
    completed: bool
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class DemandChecklistItemOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    position: int
    required: bool
    completed: bool
    completed_by_name: str | None = Field(alias="completedByName")
    completed_at: datetime | None = Field(alias="completedAt")


class DemandChecklistOut(BaseModel):
    stage_id: uuid.UUID | None = Field(alias="stageId")
    stage_name: str | None = Field(alias="stageName")
    completed: int
    total: int
    items: list[DemandChecklistItemOut]


def _category(db: Session, principal: Principal, category_id: uuid.UUID) -> DemandCategory:
    category = db.scalar(
        select(DemandCategory).where(
            DemandCategory.id == category_id,
            DemandCategory.organization_id == principal.membership.organization_id,
        )
    )
    if not category:
        raise ApiError(404, "category_not_found", "Categoria não encontrada.")
    return category


def _stage(db: Session, principal: Principal, stage_id: uuid.UUID) -> WorkflowStage:
    stage = db.scalar(
        select(WorkflowStage).where(
            WorkflowStage.id == stage_id,
            WorkflowStage.organization_id == principal.membership.organization_id,
        )
    )
    if not stage:
        raise ApiError(404, "workflow_stage_not_found", "Etapa não encontrada.")
    return stage


def _demand(db: Session, principal: Principal, demand_id: uuid.UUID, *, lock: bool = False) -> Demand:
    statement = select(Demand).where(
        Demand.id == demand_id,
        Demand.organization_id == principal.membership.organization_id,
        Demand.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    demand = db.scalar(statement)
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    return demand


def _audit(db: Session, principal: Principal, event_type: str, metadata: dict[str, object]) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type=event_type,
            metadata_json=metadata,
        )
    )


@catalog_router.get(
    "/categories/{category_id}/briefing-fields", response_model=list[BriefingFieldOut]
)
def list_briefing_fields(
    category_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[BriefingField]:
    require_permission(principal, "catalog:read")
    _category(db, principal, category_id)
    return list(
        db.scalars(
            select(BriefingField)
            .where(
                BriefingField.category_id == category_id,
                BriefingField.organization_id == principal.membership.organization_id,
            )
            .order_by(BriefingField.position, BriefingField.label)
        )
    )


@catalog_router.post(
    "/categories/{category_id}/briefing-fields",
    response_model=BriefingFieldOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_briefing_field(
    category_id: uuid.UUID,
    payload: BriefingFieldInput,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> BriefingField:
    require_permission(principal, "catalog:write")
    _category(db, principal, category_id)
    if payload.field_type == "select" and not payload.options:
        raise ApiError(422, "briefing_options_required", "Informe as opções do campo de seleção.")
    field = BriefingField(
        organization_id=principal.membership.organization_id,
        category_id=category_id,
        label=payload.label,
        key=payload.key,
        help_text=payload.help_text,
        field_type=payload.field_type,
        options=payload.options,
        required=payload.required,
        position=payload.position,
    )
    db.add(field)
    try:
        db.flush()
        _audit(db, principal, "BRIEFING_FIELD_CREATED", {"fieldId": str(field.id), "categoryId": str(category_id)})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "briefing_field_conflict", "Esta chave já existe na categoria.") from exc
    db.refresh(field)
    return field


@catalog_router.put(
    "/briefing-fields/{field_id}",
    response_model=BriefingFieldOut,
    dependencies=[Depends(require_csrf)],
)
def update_briefing_field(
    field_id: uuid.UUID,
    payload: BriefingFieldUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> BriefingField:
    require_permission(principal, "catalog:write")
    field = db.scalar(
        select(BriefingField)
        .where(
            BriefingField.id == field_id,
            BriefingField.organization_id == principal.membership.organization_id,
        )
        .with_for_update()
    )
    if not field:
        raise ApiError(404, "briefing_field_not_found", "Campo de briefing não encontrado.")
    if field.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O campo foi alterado. Atualize a tela.")
    if payload.field_type == "select" and not payload.options:
        raise ApiError(422, "briefing_options_required", "Informe as opções do campo de seleção.")
    field.label = payload.label
    field.key = payload.key
    field.help_text = payload.help_text
    field.field_type = payload.field_type
    field.options = payload.options
    field.required = payload.required
    field.position = payload.position
    field.active = payload.active
    field.revision += 1
    field.updated_at = utc_now()
    _audit(db, principal, "BRIEFING_FIELD_UPDATED", {"fieldId": str(field.id), "active": field.active})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "briefing_field_conflict", "Esta chave já existe na categoria.") from exc
    db.refresh(field)
    return field


@catalog_router.get(
    "/workflow-stages/{stage_id}/checklist-items",
    response_model=list[ChecklistTemplateOut],
)
def list_checklist_template(
    stage_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[ChecklistTemplateItem]:
    require_permission(principal, "catalog:read")
    _stage(db, principal, stage_id)
    return list(
        db.scalars(
            select(ChecklistTemplateItem)
            .where(
                ChecklistTemplateItem.workflow_stage_id == stage_id,
                ChecklistTemplateItem.organization_id == principal.membership.organization_id,
            )
            .order_by(ChecklistTemplateItem.position, ChecklistTemplateItem.title)
        )
    )


@catalog_router.post(
    "/workflow-stages/{stage_id}/checklist-items",
    response_model=ChecklistTemplateOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_checklist_template_item(
    stage_id: uuid.UUID,
    payload: ChecklistTemplateInput,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ChecklistTemplateItem:
    require_permission(principal, "catalog:write")
    _stage(db, principal, stage_id)
    item = ChecklistTemplateItem(
        organization_id=principal.membership.organization_id,
        workflow_stage_id=stage_id,
        title=payload.title,
        description=payload.description,
        position=payload.position,
        required=payload.required,
    )
    db.add(item)
    db.flush()
    _audit(db, principal, "CHECKLIST_TEMPLATE_ITEM_CREATED", {"itemId": str(item.id), "stageId": str(stage_id)})
    db.commit()
    db.refresh(item)
    return item


@catalog_router.put(
    "/checklist-items/{item_id}",
    response_model=ChecklistTemplateOut,
    dependencies=[Depends(require_csrf)],
)
def update_checklist_template_item(
    item_id: uuid.UUID,
    payload: ChecklistTemplateUpdate,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ChecklistTemplateItem:
    require_permission(principal, "catalog:write")
    item = db.scalar(
        select(ChecklistTemplateItem)
        .where(
            ChecklistTemplateItem.id == item_id,
            ChecklistTemplateItem.organization_id == principal.membership.organization_id,
        )
        .with_for_update()
    )
    if not item:
        raise ApiError(404, "checklist_item_not_found", "Item de checklist não encontrado.")
    if item.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O item foi alterado. Atualize a tela.")
    item.title = payload.title
    item.description = payload.description
    item.position = payload.position
    item.required = payload.required
    item.active = payload.active
    item.revision += 1
    item.updated_at = utc_now()
    _audit(db, principal, "CHECKLIST_TEMPLATE_ITEM_UPDATED", {"itemId": str(item.id), "active": item.active})
    db.commit()
    db.refresh(item)
    return item


@demand_router.get("/{demand_id}/briefing", response_model=DemandBriefingOut)
def get_demand_briefing(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandBriefingOut:
    require_permission(principal, "demands:read")
    demand = _demand(db, principal, demand_id)
    if not demand.category_id:
        return DemandBriefingOut(categoryId=None, categoryName=None, fields=[])
    category = _category(db, principal, demand.category_id)
    fields = list(
        db.scalars(
            select(BriefingField)
            .where(BriefingField.category_id == category.id, BriefingField.active.is_(True))
            .order_by(BriefingField.position, BriefingField.label)
        )
    )
    answers = {
        answer.field_id: answer
        for answer in db.scalars(
            select(DemandBriefingAnswer).where(DemandBriefingAnswer.demand_id == demand.id)
        )
    }
    return DemandBriefingOut(
        categoryId=category.id,
        categoryName=category.name,
        fields=[
            DemandBriefingFieldOut(
                id=field.id,
                label=field.label,
                key=field.key,
                help_text=field.help_text,
                field_type=field.field_type,
                options=field.options,
                required=field.required,
                position=field.position,
                active=field.active,
                revision=field.revision,
                value=str(answers[field.id].value) if field.id in answers and answers[field.id].value is not None else None,
            )
            for field in fields
        ],
    )


@demand_router.put(
    "/{demand_id}/briefing",
    response_model=DemandOut,
    dependencies=[Depends(require_csrf)],
)
def update_demand_briefing(
    demand_id: uuid.UUID,
    payload: DemandBriefingInput,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _demand(db, principal, demand_id, lock=True)
    if demand.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "A demanda foi alterada. Atualize a tela.")
    if not demand.category_id:
        raise ApiError(422, "briefing_requires_category", "Selecione uma categoria para preencher o briefing.")
    fields = list(
        db.scalars(
            select(BriefingField).where(
                BriefingField.category_id == demand.category_id,
                BriefingField.organization_id == principal.membership.organization_id,
                BriefingField.active.is_(True),
            )
        )
    )
    by_id = {field.id: field for field in fields}
    submitted = {answer.field_id: answer.value.strip() if answer.value else None for answer in payload.answers}
    if not set(submitted).issubset(by_id):
        raise ApiError(422, "briefing_field_invalid", "O briefing contém um campo indisponível.")
    missing = [field.label for field in fields if field.required and not submitted.get(field.id)]
    if missing:
        raise ApiError(422, "briefing_required", f"Preencha os campos obrigatórios: {', '.join(missing)}.")
    for field in fields:
        value = submitted.get(field.id)
        if field.field_type == "select" and value and value not in field.options:
            raise ApiError(422, "briefing_option_invalid", f"Selecione uma opção válida em {field.label}.")
        if field.field_type == "number" and value:
            try:
                float(value.replace(",", "."))
            except ValueError as exc:
                raise ApiError(422, "briefing_number_invalid", f"Informe um número válido em {field.label}.") from exc
    existing = {
        answer.field_id: answer
        for answer in db.scalars(
            select(DemandBriefingAnswer).where(DemandBriefingAnswer.demand_id == demand.id)
        )
    }
    for field in fields:
        answer = existing.get(field.id)
        if answer:
            answer.value = submitted.get(field.id)
            answer.updated_by = principal.profile.id
            answer.revision += 1
            answer.updated_at = utc_now()
        else:
            db.add(
                DemandBriefingAnswer(
                    demand_id=demand.id,
                    field_id=field.id,
                    value=submitted.get(field.id),
                    updated_by=principal.profile.id,
                )
            )
    demand.revision += 1
    demand.updated_at = utc_now()
    db.add(
        DemandUpdate(
            demand_id=demand.id,
            created_by=principal.profile.id,
            kind="BRIEFING_UPDATED",
            summary="Briefing atualizado.",
            payload={"fieldCount": len(fields)},
        )
    )
    _audit(db, principal, "DEMAND_BRIEFING_UPDATED", {"demandId": str(demand.id), "fieldCount": len(fields)})
    db.commit()
    db.refresh(demand)
    return demand_out(db, demand)


@demand_router.get("/{demand_id}/checklist", response_model=DemandChecklistOut)
def get_demand_checklist(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandChecklistOut:
    require_permission(principal, "demands:read")
    demand = _demand(db, principal, demand_id)
    if not demand.current_stage_id:
        return DemandChecklistOut(stageId=None, stageName=None, completed=0, total=0, items=[])
    stage = _stage(db, principal, demand.current_stage_id)
    templates = list(
        db.scalars(
            select(ChecklistTemplateItem)
            .where(
                ChecklistTemplateItem.workflow_stage_id == stage.id,
                ChecklistTemplateItem.active.is_(True),
            )
            .order_by(ChecklistTemplateItem.position, ChecklistTemplateItem.title)
        )
    )
    records = {
        record.template_item_id: record
        for record in db.scalars(
            select(DemandChecklistItem).where(DemandChecklistItem.demand_id == demand.id)
        )
    }
    items: list[DemandChecklistItemOut] = []
    for template in templates:
        record = records.get(template.id)
        completed_by = db.get(UserProfile, record.completed_by) if record and record.completed_by else None
        items.append(
            DemandChecklistItemOut(
                id=template.id,
                title=template.title,
                description=template.description,
                position=template.position,
                required=template.required,
                completed=record.completed if record else False,
                completedByName=completed_by.full_name if completed_by else None,
                completedAt=record.completed_at if record else None,
            )
        )
    return DemandChecklistOut(
        stageId=stage.id,
        stageName=stage.name,
        completed=sum(item.completed for item in items),
        total=len(items),
        items=items,
    )


@demand_router.patch(
    "/{demand_id}/checklist/{template_item_id}",
    response_model=DemandOut,
    dependencies=[Depends(require_csrf)],
)
def toggle_demand_checklist_item(
    demand_id: uuid.UUID,
    template_item_id: uuid.UUID,
    payload: ChecklistToggleInput,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DemandOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _demand(db, principal, demand_id, lock=True)
    if demand.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "A demanda foi alterada. Atualize a tela.")
    template = db.scalar(
        select(ChecklistTemplateItem).where(
            ChecklistTemplateItem.id == template_item_id,
            ChecklistTemplateItem.organization_id == principal.membership.organization_id,
            ChecklistTemplateItem.workflow_stage_id == demand.current_stage_id,
            ChecklistTemplateItem.active.is_(True),
        )
    )
    if not template:
        raise ApiError(422, "checklist_item_invalid", "O item não pertence à etapa atual.")
    record = db.scalar(
        select(DemandChecklistItem)
        .where(
            DemandChecklistItem.demand_id == demand.id,
            DemandChecklistItem.template_item_id == template.id,
        )
        .with_for_update()
    )
    now = utc_now()
    if record:
        record.completed = payload.completed
        record.completed_by = principal.profile.id if payload.completed else None
        record.completed_at = now if payload.completed else None
        record.revision += 1
        record.updated_at = now
    else:
        db.add(
            DemandChecklistItem(
                demand_id=demand.id,
                template_item_id=template.id,
                completed=payload.completed,
                completed_by=principal.profile.id if payload.completed else None,
                completed_at=now if payload.completed else None,
            )
        )
    demand.revision += 1
    demand.updated_at = now
    db.add(
        DemandUpdate(
            demand_id=demand.id,
            created_by=principal.profile.id,
            kind="CHECKLIST_UPDATED",
            summary=f"Checklist: {template.title}.",
            payload={"templateItemId": str(template.id), "completed": payload.completed},
        )
    )
    _audit(db, principal, "DEMAND_CHECKLIST_UPDATED", {"demandId": str(demand.id), "templateItemId": str(template.id), "completed": payload.completed})
    db.commit()
    db.refresh(demand)
    return demand_out(db, demand)
