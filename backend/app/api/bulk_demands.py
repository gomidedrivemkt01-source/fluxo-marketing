"""Criação em lote, com revisão, chaves estáveis e gravação atômica por organização."""

import hashlib
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.access import require_any_permission, require_permission
from app.api.demands import create_demand_record, resolve_stage_assignee
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import (
    AuditEvent,
    BriefingField,
    BulkDemandBatch,
    BulkDemandItem,
    Company,
    Demand,
    DemandBriefingAnswer,
    DemandCategory,
    DemandStageInstance,
    DemandStageVisit,
    DemandTodoItem,
    DemandUpdate,
    Membership,
    MembershipStatus,
    Organization,
    UserProfile,
    Workflow,
    WorkflowStage,
)

router = APIRouter(prefix="/bulk-demands", tags=["Demandas em massa"])
Key = str


class BulkCard(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    externalId: Key = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:/-]+$")
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    companyCode: str | None = Field(default=None, max_length=100)
    categoryCode: str | None = Field(default=None, max_length=100)
    workflowCode: str | None = Field(default=None, max_length=100)
    stageCode: str | None = Field(default=None, max_length=100)
    assigneeEmail: str | None = Field(default=None, max_length=254)
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] = "NORMAL"
    deadlineAt: AwareDatetime | None = None
    briefing: dict[str, str] = Field(default_factory=dict, max_length=100)
    checklist: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def clean_content(self) -> "BulkCard":
        if len(" ".join(self.title.split())) < 2:
            raise ValueError("O título precisa ter pelo menos dois caracteres.")
        if any(not item.strip() or len(item) > 240 for item in self.checklist):
            raise ValueError("Cada item do checklist deve ter entre 1 e 240 caracteres.")
        if any(len(value) > 10000 for value in self.briefing.values()):
            raise ValueError("Cada resposta de briefing deve ter no máximo 10.000 caracteres.")
        return self


class BulkDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schemaVersion: Literal["fluxo.demands.v1"]
    batchId: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:/-]+$")
    cards: list[BulkCard] = Field(min_length=1, max_length=200)
    guide: dict[str, Any] | None = None

    @model_validator(mode="after")
    def stable_keys(self) -> "BulkDocument":
        keys = [item.externalId for item in self.cards]
        if len(keys) != len(set(keys)):
            raise ValueError("O mesmo externalId aparece mais de uma vez no arquivo.")
        if (
            len(json.dumps(self.model_dump(mode="json"), ensure_ascii=False).encode())
            > 5 * 1024 * 1024
        ):
            raise ValueError("O lote deve ter no máximo 5 MB.")
        return self


class BulkRequest(BaseModel):
    document: BulkDocument
    previewHash: str | None = Field(default=None, max_length=64)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def document_hash(document: BulkDocument) -> str:
    return digest(document.model_dump(mode="json", exclude={"guide"}, exclude_unset=True))


def catalogs(db: Session, principal: Principal) -> dict[str, Any]:
    org = principal.membership.organization_id

    def active(model: Any) -> list[Any]:
        return list(
            db.scalars(select(model).where(model.organization_id == org, model.active.is_(True)))
        )

    people = (
        db.execute(
            select(UserProfile)
            .join(Membership, Membership.user_profile_id == UserProfile.id)
            .where(
                Membership.organization_id == org,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.removed_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    workflows = [item for item in active(Workflow) if item.lifecycle_state == "PUBLISHED"]
    return {
        "companies": active(Company),
        "categories": active(DemandCategory),
        "workflows": workflows,
        "stages": active(WorkflowStage),
        "people": list(people),
        "fields": active(BriefingField),
    }


def plan(document: BulkDocument, db: Session, principal: Principal) -> dict[str, Any]:
    data = catalogs(db, principal)
    existing = {
        key: demand_id
        for key, demand_id in db.execute(
            select(BulkDemandItem.external_key, BulkDemandItem.demand_id).where(
                BulkDemandItem.organization_id == principal.membership.organization_id,
                BulkDemandItem.external_key.in_([card.externalId for card in document.cards]),
            )
        ).all()
    }
    rows = []
    for index, card in enumerate(document.cards):
        errors: list[dict[str, str]] = []

        def find(
            collection: str, code: str | None, field: str, errors: list[dict[str, str]] = errors
        ) -> Any:
            if code is None:
                return None
            found = next((item for item in data[collection] if item.code == code), None)
            if found is None:
                errors.append(
                    {
                        "field": field,
                        "message": f"Código não disponível: {code}. Use o catálogo do modelo atualizado.",
                    }
                )
            return found

        company = find("companies", card.companyCode, "companyCode")
        category = find("categories", card.categoryCode, "categoryCode")
        workflow = find("workflows", card.workflowCode, "workflowCode")
        if card.workflowCode is None:
            default_id = category.default_workflow_id if category else None
            workflow = (
                next((item for item in data["workflows"] if item.id == default_id), None)
                if default_id
                else next((item for item in data["workflows"] if item.is_default), None)
            )
        if workflow is None:
            errors.append(
                {
                    "field": "workflowCode",
                    "message": "Nenhum workflow publicado disponível para este card.",
                }
            )
        stages = sorted(
            [item for item in data["stages"] if workflow and item.workflow_id == workflow.id],
            key=lambda item: item.position,
        )
        stage = (
            next((item for item in stages if item.code == card.stageCode), None)
            if card.stageCode
            else next(iter(stages), None)
        )
        if stage is None:
            errors.append(
                {
                    "field": "stageCode",
                    "message": "Escolha uma etapa ativa pertencente ao workflow indicado.",
                }
            )
        person = (
            next(
                (
                    item
                    for item in data["people"]
                    if item.email.casefold() == (card.assigneeEmail or "").casefold()
                ),
                None,
            )
            if card.assigneeEmail
            else None
        )
        if card.assigneeEmail and person is None:
            errors.append(
                {
                    "field": "assigneeEmail",
                    "message": "Este responsável não tem acesso ativo à organização.",
                }
            )
        assignee_id = person.id if person else None
        inherit = "assigneeEmail" not in card.model_fields_set
        if inherit and stage:
            assignee_id = resolve_stage_assignee(
                db,
                Demand(organization_id=principal.membership.organization_id),
                default_assignee_id=stage.default_assignee_id,
                owner_role_id=stage.owner_role_id,
                fallback_user_id=stage.fallback_user_id,
            )
        fields = {
            item.key: item
            for item in data["fields"]
            if category and item.category_id == category.id
        }
        for key, value in card.briefing.items():
            item = fields.get(key)
            if not item:
                errors.append(
                    {
                        "field": f"briefing.{key}",
                        "message": "Esta chave não pertence ao briefing da categoria.",
                    }
                )
            elif item.field_type == "select" and value and value not in item.options:
                errors.append(
                    {
                        "field": f"briefing.{key}",
                        "message": "Escolha uma opção do briefing no catálogo.",
                    }
                )
            elif item.field_type == "number" and value:
                try:
                    float(value.replace(",", "."))
                except ValueError:
                    errors.append(
                        {"field": f"briefing.{key}", "message": "Informe um número válido."}
                    )
        resolved = {
            "companyId": str(company.id) if company else None,
            "categoryId": str(category.id) if category else None,
            "workflowId": str(workflow.id) if workflow else None,
            "stageId": str(stage.id) if stage else None,
            "assigneeId": str(assignee_id) if assignee_id else None,
            "workflowRevision": workflow.revision if workflow else None,
            "stageRevision": stage.revision if stage else None,
            "briefingFields": {
                key: {"id": str(item.id), "revision": item.revision} for key, item in fields.items()
            },
        }
        assignee_name = next(
            (item.full_name for item in data["people"] if item.id == assignee_id), None
        )
        rows.append(
            {
                "index": index + 1,
                "externalId": card.externalId,
                "title": card.title,
                "company": company.name if company else "Sem empresa",
                "category": category.name if category else "Sem categoria",
                "workflow": workflow.name if workflow else "—",
                "stage": stage.name if stage else "—",
                "assignee": assignee_name or "Sem responsável",
                "deadlineAt": card.deadlineAt.isoformat() if card.deadlineAt else None,
                "state": "duplicate"
                if card.externalId in existing
                else "invalid"
                if errors
                else "ready",
                "existingDemandId": str(existing[card.externalId])
                if card.externalId in existing
                else None,
                "errors": errors,
                "resolved": resolved,
            }
        )
    return {
        "rows": rows,
        "ready": sum(row["state"] == "ready" for row in rows),
        "duplicates": sum(row["state"] == "duplicate" for row in rows),
        "invalid": sum(row["state"] == "invalid" for row in rows),
        "previewHash": digest({"document": document_hash(document), "rows": rows}),
    }


@router.get("/model")
def model_file(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> JSONResponse:
    require_permission(principal, "demands:read")
    data = catalogs(db, principal)
    guide = {
        "instructions": "Crie um card por material/post. Retorne somente JSON válido com schemaVersion, batchId e cards, sem Markdown. Preserve externalId e batchId ao reenviar a mesma linha editorial. Substitua os dados de exemplo; não invente códigos nem pessoas. Datas ISO 8601 devem conter fuso, exemplo 2026-11-20T17:00:00-03:00. Use null para datas desconhecidas. Não adivinhe datas ou responsáveis. Máximo 200 cards e 5 MB. guide pode ser removido do resultado.",
        "identity": "externalId é único em toda a organização. Use marca-periodo-tipo-sequencia. Reenviar chaves já criadas não duplica nem atualiza o card existente. batchId identifica a versão exata do lote; use outro batchId se o conteúdo mudar, preservando os externalId dos mesmos cards.",
        "defaults": "companyCode e categoryCode podem ser null. workflowCode omitido/null usa o padrão da categoria ou da plataforma. stageCode omitido/null usa a primeira etapa. assigneeEmail omitido herda o responsável da função; null deixa sem responsável; e-mail aplica uma pessoa específica. priority: LOW, NORMAL, HIGH ou URGENT. briefing usa as chaves da categoria. checklist acrescenta tarefas personalizadas, sem marcar como concluídas as obrigações do workflow.",
        "companies": [{"code": item.code, "name": item.name} for item in data["companies"]],
        "categories": [
            {
                "code": item.code,
                "name": item.name,
                "defaultWorkflowCode": next(
                    (w.code for w in data["workflows"] if w.id == item.default_workflow_id), None
                ),
                "briefing": [
                    {
                        "key": f.key,
                        "label": f.label,
                        "type": f.field_type,
                        "required": f.required,
                        "options": f.options,
                    }
                    for f in data["fields"]
                    if f.category_id == item.id
                ],
            }
            for item in data["categories"]
        ],
        "workflows": [
            {
                "code": item.code,
                "name": item.name,
                "isDefault": item.is_default,
                "stages": [
                    {"code": s.code, "name": s.name}
                    for s in sorted(data["stages"], key=lambda s: s.position)
                    if s.workflow_id == item.id
                ],
            }
            for item in data["workflows"]
        ],
        "people": [{"name": item.full_name, "email": item.email} for item in data["people"]],
    }
    document = {
        "schemaVersion": "fluxo.demands.v1",
        "batchId": "linha-editorial-AAAA-MM-v1",
        "guide": guide,
        "cards": [
            {
                "externalId": "marca-AAAA-MM-post-001",
                "title": "Substitua pelo título do material",
                "description": "Briefing, texto, objetivo e instruções do post.",
                "companyCode": None,
                "categoryCode": None,
                "workflowCode": None,
                "stageCode": None,
                "assigneeEmail": None,
                "priority": "NORMAL",
                "deadlineAt": None,
                "briefing": {},
                "checklist": ["Revisar texto e referências", "Preparar o material"],
            }
        ],
    }
    return JSONResponse(
        document,
        headers={"Content-Disposition": 'attachment; filename="modelo-demandas-fluxo.json"'},
    )


@router.get("/schema")
def schema_file(principal: Principal = Depends(get_principal)) -> JSONResponse:
    require_permission(principal, "demands:read")
    return JSONResponse(
        BulkDocument.model_json_schema(),
        headers={"Content-Disposition": 'attachment; filename="schema-demandas-fluxo.json"'},
    )


@router.post("/preview", dependencies=[Depends(require_csrf)])
def preview(
    payload: BulkRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_any_permission(principal, "demands:write", "demands:work")
    result = plan(payload.document, db, principal)
    for row in result["rows"]:
        row.pop("resolved")
    return result


@router.post("/apply", dependencies=[Depends(require_csrf)])
def apply(
    payload: BulkRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_any_permission(principal, "demands:write", "demands:work")
    org = principal.membership.organization_id
    # Impede duas importações concorrentes de criar a mesma chave no mesmo ambiente.
    db.execute(select(Organization.id).where(Organization.id == org).with_for_update())
    old = db.scalar(
        select(BulkDemandBatch).where(
            BulkDemandBatch.organization_id == org,
            BulkDemandBatch.batch_key == payload.document.batchId,
        )
    )
    fingerprint = document_hash(payload.document)
    if old:
        if old.document_hash != fingerprint:
            raise ApiError(
                409,
                "batch_content_changed",
                "Este batchId já foi usado com outro conteúdo. Use uma nova versão do lote mantendo os externalId dos mesmos cards.",
            )
        return {**old.result, "alreadyApplied": True}
    result = plan(payload.document, db, principal)
    if result["invalid"]:
        raise ApiError(
            422, "bulk_invalid", "Corrija os cards sinalizados e valide o arquivo novamente."
        )
    if not payload.previewHash or payload.previewHash != result["previewHash"]:
        raise ApiError(
            409,
            "bulk_preview_changed",
            "O arquivo ou os cadastros mudaram. Revise uma nova prévia antes de criar o lote.",
        )
    batch = BulkDemandBatch(
        organization_id=org,
        created_by=principal.profile.id,
        batch_key=payload.document.batchId,
        document_hash=fingerprint,
        result={},
    )
    db.add(batch)
    db.flush()
    created = []
    for card, row in zip(payload.document.cards, result["rows"], strict=True):
        if row["state"] != "ready":
            continue
        from uuid import UUID

        resolved = row["resolved"]

        def uid(key: str, resolved: dict[str, Any] = resolved) -> Any:
            return UUID(resolved[key]) if resolved[key] else None

        demand = create_demand_record(
            db,
            principal,
            title=card.title,
            description=card.description,
            company_id=uid("companyId"),
            category_id=uid("categoryId"),
            workflow_id=uid("workflowId"),
            stage_id=uid("stageId"),
            assignee_id=uid("assigneeId"),
            inherit_assignee=False,
            priority=card.priority,
            deadline_at=card.deadlineAt,
            source="bulk_json",
        )
        # Mantém sem responsável também no plano/visita quando o JSON pede null.
        for instance in db.scalars(
            select(DemandStageInstance).where(
                DemandStageInstance.demand_id == demand.id,
                DemandStageInstance.workflow_stage_id == demand.current_stage_id,
            )
        ):
            instance.assignee_id = demand.current_assignee_id
        for visit in db.scalars(
            select(DemandStageVisit).where(DemandStageVisit.demand_id == demand.id)
        ):
            visit.assignee_id = demand.current_assignee_id
        for key, value in card.briefing.items():
            db.add(
                DemandBriefingAnswer(
                    demand_id=demand.id,
                    field_id=UUID(resolved["briefingFields"][key]["id"]),
                    value=value or None,
                    updated_by=principal.profile.id,
                )
            )
        for position, title in enumerate(card.checklist, 1):
            db.add(
                DemandTodoItem(
                    organization_id=org,
                    demand_id=demand.id,
                    title=title.strip(),
                    position=position,
                    created_by=principal.profile.id,
                    source_system="bulk_json",
                    external_id=f"item-{position}",
                )
            )
        db.add(
            BulkDemandItem(
                organization_id=org,
                batch_id=batch.id,
                external_key=card.externalId,
                demand_id=demand.id,
            )
        )
        db.add(
            DemandUpdate(
                demand_id=demand.id,
                created_by=principal.profile.id,
                kind="BULK_DEMAND_CREATED",
                summary="Demanda criada por lote JSON revisado.",
                payload={
                    "batchId": str(batch.id),
                    "externalId": card.externalId,
                    "batchKey": payload.document.batchId,
                },
            )
        )
        created.append({"id": str(demand.id), "publicId": demand.public_id, "title": demand.title})
    output = {
        "batchId": str(batch.id),
        "created": len(created),
        "skipped": result["duplicates"],
        "demands": created,
        "alreadyApplied": False,
    }
    batch.result = output
    db.add(
        AuditEvent(
            organization_id=org,
            actor_user_id=principal.profile.id,
            event_type="BULK_DEMANDS_CREATED",
            metadata_json={
                "batchId": str(batch.id),
                "batchKey": batch.batch_key,
                "created": len(created),
                "skipped": result["duplicates"],
            },
        )
    )
    db.commit()
    return output


@router.get("/history")
def history(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    require_permission(principal, "demands:read")
    query = select(BulkDemandBatch).where(
        BulkDemandBatch.organization_id == principal.membership.organization_id
    )
    if not (
        principal.role
        and ("*" in principal.role.permissions or "demands:write" in principal.role.permissions)
    ):
        query = query.where(BulkDemandBatch.created_by == principal.profile.id)
    return [
        {
            "id": str(item.id),
            "batchId": item.batch_key,
            "createdAt": item.created_at.isoformat(),
            "created": item.result.get("created", 0),
            "skipped": item.result.get("skipped", 0),
        }
        for item in db.scalars(query.order_by(BulkDemandBatch.created_at.desc()).limit(50))
    ]
