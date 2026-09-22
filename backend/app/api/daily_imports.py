import hashlib
import json
import uuid
from datetime import UTC, date, datetime, time
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.access import require_permission
from app.api.demands import create_demand_record
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import (
    AuditEvent,
    DailyImport,
    DailyImportItem,
    Demand,
    DemandUpdate,
    utc_now,
)

router = APIRouter(prefix="/imports/dailys", tags=["Importação de Dailys"])

ProposalType = Literal[
    "ADD_COMMENT",
    "SET_FORECAST",
    "SET_DEADLINE",
    "SET_STATUS",
    "SUGGEST_ASSIGNEE",
    "SUGGEST_STAGE",
]
ALLOWED_STATUS = {
    "WAITING_EXECUTION",
    "IN_PROGRESS",
    "WAITING_INFORMATION",
    "WAITING_APPROVAL",
    "BLOCKED",
    "SCHEDULED",
    "COMPLETED",
}


class DailySource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["DAILY_REPORT"]
    date: date
    label: str = Field(min_length=1, max_length=200)


class DailyReference(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title_hint: str = Field(alias="titleHint", min_length=1, max_length=300)
    company_hint: str | None = Field(default=None, alias="companyHint", max_length=200)
    card_id_hint: str | None = Field(
        default=None, alias="cardIdHint", pattern=r"^DMD-[0-9]{4}-[0-9]{6,}$"
    )


class DailyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    proposal_id: str = Field(alias="proposalId", pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
    type: ProposalType
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_payload(self) -> "DailyProposal":
        if self.type == "ADD_COMMENT":
            value = self.payload.get("text")
            if (
                set(self.payload) != {"text"}
                or not isinstance(value, str)
                or not 1 <= len(value) <= 5000
            ):
                raise ValueError("ADD_COMMENT exige somente o campo text.")
        elif self.type in {"SET_FORECAST", "SET_DEADLINE"}:
            value = self.payload.get("value")
            if set(self.payload) != {"value"} or not isinstance(value, str):
                raise ValueError(f"{self.type} exige somente o campo value.")
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Data e hora inválidas.") from exc
        elif self.type == "SET_STATUS":
            if set(self.payload) != {"value"} or self.payload.get("value") not in ALLOWED_STATUS:
                raise ValueError("Status inválido.")
        else:
            value = self.payload.get("hint")
            if (
                set(self.payload) != {"hint"}
                or not isinstance(value, str)
                or not 1 <= len(value) <= 200
            ):
                raise ValueError(f"{self.type} exige somente o campo hint.")
        return self


class DailyDocumentItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    item_id: str = Field(alias="itemId", pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
    reference: DailyReference
    summary: str = Field(min_length=1, max_length=3000)
    source_excerpt: str = Field(alias="sourceExcerpt", min_length=1, max_length=5000)
    proposals: list[DailyProposal] = Field(min_length=1, max_length=20)


class DailyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["2.0"] = Field(alias="schemaVersion")
    import_type: Literal["DAILY_REVIEW"] = Field(alias="importType")
    batch_id: str = Field(alias="batchId", pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
    source: DailySource
    items: list[DailyDocumentItem] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_ids(self) -> "DailyDocument":
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("itemId precisa ser único no arquivo.")
        return self


class CreateDailyImport(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    document: DailyDocument


class MappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    action: Literal["map", "create", "ignore"]
    target_demand_id: uuid.UUID | None = Field(default=None, alias="targetDemandId")
    new_demand_title: str | None = Field(default=None, alias="newDemandTitle", max_length=300)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid_choice(self) -> "MappingRequest":
        if self.action == "map" and not self.target_demand_id:
            raise ValueError("Escolha o card de destino.")
        if self.action == "create" and not (self.new_demand_title or "").strip():
            raise ValueError("Informe o título do novo card.")
        return self


class DailyItemOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    item_id: str = Field(alias="itemId")
    title_hint: str = Field(alias="titleHint")
    company_hint: str | None = Field(alias="companyHint")
    card_id_hint: str | None = Field(alias="cardIdHint")
    summary: str
    source_excerpt: str = Field(alias="sourceExcerpt")
    proposals: list[dict[str, Any]]
    action: str
    target_demand_id: uuid.UUID | None = Field(alias="targetDemandId")
    target_public_id: str | None = Field(alias="targetPublicId")
    target_title: str | None = Field(alias="targetTitle")
    new_demand_title: str | None = Field(alias="newDemandTitle")
    note: str | None


class DailyImportOut(BaseModel):
    id: uuid.UUID
    filename: str
    batch_id: str = Field(alias="batchId")
    source_date: datetime = Field(alias="sourceDate")
    source_label: str = Field(alias="sourceLabel")
    state: str
    total_items: int = Field(alias="totalItems")
    reviewed_items: int = Field(alias="reviewedItems")
    items: list[DailyItemOut]


class ApplyResult(BaseModel):
    message: str
    updated: int
    created: int
    ignored: int


def import_out(db: Session, daily: DailyImport) -> DailyImportOut:
    items = list(
        db.scalars(
            select(DailyImportItem)
            .where(DailyImportItem.daily_import_id == daily.id)
            .order_by(DailyImportItem.ordinal)
        )
    )
    output_items: list[DailyItemOut] = []
    for item in items:
        demand = db.get(Demand, item.target_demand_id) if item.target_demand_id else None
        output_items.append(
            DailyItemOut(
                id=item.id,
                ordinal=item.ordinal,
                itemId=item.source_item_id,
                titleHint=item.title_hint,
                companyHint=item.company_hint,
                cardIdHint=item.card_id_hint,
                summary=item.summary,
                sourceExcerpt=item.source_excerpt,
                proposals=item.proposals,
                action=item.mapping_action,
                targetDemandId=item.target_demand_id,
                targetPublicId=demand.public_id if demand else None,
                targetTitle=demand.title if demand else None,
                newDemandTitle=item.new_demand_title,
                note=item.mapping_note,
            )
        )
    return DailyImportOut(
        id=daily.id,
        filename=daily.filename,
        batchId=daily.batch_id,
        sourceDate=daily.source_date,
        sourceLabel=daily.source_label,
        state=daily.state,
        totalItems=len(items),
        reviewedItems=sum(item.mapping_action != "pending" for item in items),
        items=output_items,
    )


@router.post(
    "", response_model=DailyImportOut, status_code=201, dependencies=[Depends(require_csrf)]
)
def create_import(
    payload: CreateDailyImport,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DailyImportOut:
    require_permission(principal, "imports:write")
    document = payload.document.model_dump(by_alias=True, mode="json")
    document_hash = hashlib.sha256(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = db.scalar(
        select(DailyImport).where(
            DailyImport.organization_id == principal.membership.organization_id,
            DailyImport.document_hash == document_hash,
        )
    )
    if existing:
        raise ApiError(409, "daily_already_uploaded", "Este JSON já foi enviado anteriormente.")
    daily = DailyImport(
        organization_id=principal.membership.organization_id,
        uploaded_by=principal.profile.id,
        filename=payload.filename,
        batch_id=payload.document.batch_id,
        source_date=datetime.combine(payload.document.source.date, time.min, tzinfo=UTC),
        source_label=payload.document.source.label,
        schema_version=payload.document.schema_version,
        document_hash=document_hash,
        raw_document=document,
    )
    db.add(daily)
    db.flush()
    for ordinal, source_item in enumerate(payload.document.items, start=1):
        db.add(
            DailyImportItem(
                daily_import_id=daily.id,
                ordinal=ordinal,
                source_item_id=source_item.item_id,
                title_hint=source_item.reference.title_hint,
                company_hint=source_item.reference.company_hint,
                card_id_hint=source_item.reference.card_id_hint,
                summary=source_item.summary,
                source_excerpt=source_item.source_excerpt,
                proposals=[
                    proposal.model_dump(by_alias=True, mode="json")
                    for proposal in source_item.proposals
                ],
            )
        )
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type="DAILY_IMPORT_UPLOADED",
            source="json_import",
            metadata_json={
                "importId": str(daily.id),
                "filename": payload.filename,
                "items": len(payload.document.items),
            },
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            409, "daily_already_uploaded", "Este JSON já foi enviado anteriormente."
        ) from exc
    return import_out(db, daily)


@router.get("", response_model=list[DailyImportOut])
def list_imports(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[DailyImportOut]:
    require_permission(principal, "imports:write")
    imports = db.scalars(
        select(DailyImport)
        .where(DailyImport.organization_id == principal.membership.organization_id)
        .order_by(DailyImport.created_at.desc())
        .limit(20)
    )
    return [import_out(db, daily) for daily in imports]


@router.get("/{import_id}", response_model=DailyImportOut)
def get_import(
    import_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DailyImportOut:
    require_permission(principal, "imports:write")
    daily = db.scalar(
        select(DailyImport).where(
            DailyImport.id == import_id,
            DailyImport.organization_id == principal.membership.organization_id,
        )
    )
    if not daily:
        raise ApiError(404, "daily_not_found", "Importação não encontrada.")
    return import_out(db, daily)


@router.put(
    "/{import_id}/items/{item_id}",
    response_model=DailyImportOut,
    dependencies=[Depends(require_csrf)],
)
def map_item(
    import_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: MappingRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DailyImportOut:
    require_permission(principal, "imports:write")
    daily = db.scalar(
        select(DailyImport).where(
            DailyImport.id == import_id,
            DailyImport.organization_id == principal.membership.organization_id,
        )
    )
    if not daily:
        raise ApiError(404, "daily_not_found", "Importação não encontrada.")
    if daily.state != "reviewing":
        raise ApiError(409, "daily_closed", "Esta importação já foi encerrada.")
    item = db.scalar(
        select(DailyImportItem).where(
            DailyImportItem.id == item_id,
            DailyImportItem.daily_import_id == daily.id,
        )
    )
    if not item:
        raise ApiError(404, "daily_item_not_found", "Item da Daily não encontrado.")
    if payload.action == "map":
        demand = db.scalar(
            select(Demand).where(
                Demand.id == payload.target_demand_id,
                Demand.organization_id == principal.membership.organization_id,
                Demand.deleted_at.is_(None),
            )
        )
        if not demand:
            raise ApiError(422, "target_demand_not_found", "O card escolhido não está disponível.")
    item.mapping_action = payload.action
    item.target_demand_id = payload.target_demand_id if payload.action == "map" else None
    item.new_demand_title = (
        payload.new_demand_title.strip()
        if payload.action == "create" and payload.new_demand_title
        else None
    )
    item.mapping_note = payload.note
    item.reviewed_by = principal.profile.id
    item.reviewed_at = utc_now()
    db.commit()
    return import_out(db, daily)


def apply_proposal(
    db: Session,
    principal: Principal,
    demand: Demand,
    item: DailyImportItem,
    proposal: dict[str, Any],
) -> None:
    proposal_type = str(proposal["type"])
    payload = dict(proposal["payload"])
    summary = item.summary
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    if proposal_type == "SET_STATUS":
        before["status"] = demand.status
        demand.status = str(payload["value"])
        after["status"] = demand.status
    elif proposal_type == "SET_FORECAST":
        before["forecastAt"] = demand.forecast_at.isoformat() if demand.forecast_at else None
        demand.forecast_at = datetime.fromisoformat(str(payload["value"]).replace("Z", "+00:00"))
        after["forecastAt"] = demand.forecast_at.isoformat()
    elif proposal_type == "SET_DEADLINE":
        before["deadlineAt"] = demand.deadline_at.isoformat() if demand.deadline_at else None
        demand.deadline_at = datetime.fromisoformat(str(payload["value"]).replace("Z", "+00:00"))
        after["deadlineAt"] = demand.deadline_at.isoformat()
    elif proposal_type == "ADD_COMMENT":
        summary = str(payload["text"])
    else:
        summary = f"Sugestão da Daily: {payload['hint']}"
    db.add(
        DemandUpdate(
            demand_id=demand.id,
            daily_import_item_id=item.id,
            created_by=principal.profile.id,
            kind=proposal_type,
            summary=summary,
            payload={"proposal": proposal, "before": before, "after": after},
        )
    )


@router.post(
    "/{import_id}/apply",
    response_model=ApplyResult,
    dependencies=[Depends(require_csrf)],
)
def apply_import(
    import_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ApplyResult:
    require_permission(principal, "imports:write")
    daily = db.scalar(
        select(DailyImport)
        .where(
            DailyImport.id == import_id,
            DailyImport.organization_id == principal.membership.organization_id,
        )
        .with_for_update()
    )
    if not daily:
        raise ApiError(404, "daily_not_found", "Importação não encontrada.")
    if daily.state != "reviewing":
        raise ApiError(409, "daily_closed", "Esta importação já foi encerrada.")
    items = list(
        db.scalars(
            select(DailyImportItem)
            .where(DailyImportItem.daily_import_id == daily.id)
            .order_by(DailyImportItem.ordinal)
        )
    )
    if any(item.mapping_action == "pending" for item in items):
        raise ApiError(409, "daily_review_incomplete", "Revise todos os itens antes de aplicar.")
    created = updated = ignored = 0
    for item in items:
        if item.mapping_action == "ignore":
            ignored += 1
            item.applied_at = utc_now()
            continue
        if item.mapping_action == "create":
            demand = create_demand_record(
                db,
                principal,
                title=item.new_demand_title or item.title_hint,
                description=item.source_excerpt,
                source="json_import",
            )
            item.target_demand_id = demand.id
            created += 1
        else:
            mapped_demand = db.scalar(
                select(Demand)
                .where(
                    Demand.id == item.target_demand_id,
                    Demand.organization_id == principal.membership.organization_id,
                    Demand.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if not mapped_demand:
                raise ApiError(
                    409,
                    "target_demand_unavailable",
                    f"O destino do item {item.source_item_id} mudou.",
                )
            demand = mapped_demand
            updated += 1
        db.add(
            DemandUpdate(
                demand_id=demand.id,
                daily_import_item_id=item.id,
                created_by=principal.profile.id,
                kind="DAILY_CONTEXT",
                summary=item.summary,
                payload={"sourceExcerpt": item.source_excerpt, "mappingNote": item.mapping_note},
            )
        )
        for proposal in item.proposals:
            apply_proposal(db, principal, demand, item, proposal)
        demand.revision += 1
        demand.updated_at = utc_now()
        item.applied_at = utc_now()
        db.add(
            AuditEvent(
                organization_id=principal.membership.organization_id,
                actor_user_id=principal.profile.id,
                event_type="DAILY_ITEM_APPLIED",
                source="json_import",
                metadata_json={
                    "importId": str(daily.id),
                    "itemId": item.source_item_id,
                    "demandId": str(demand.id),
                    "publicId": demand.public_id,
                    "action": item.mapping_action,
                },
            )
        )
    daily.state = "applied"
    daily.applied_at = utc_now()
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type="DAILY_IMPORT_APPLIED",
            source="json_import",
            metadata_json={
                "importId": str(daily.id),
                "created": created,
                "updated": updated,
                "ignored": ignored,
            },
        )
    )
    db.commit()
    return ApplyResult(
        message="Daily aplicada com histórico individual por card.",
        updated=updated,
        created=created,
        ignored=ignored,
    )
