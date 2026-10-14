"""Governança administrativa: Trello, histórico, restauração e retenção."""

import hashlib
import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.demands import ensure_workflow_version
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.governance import (
    best_named_match,
    canonical_hash,
    card_snapshot,
    parse_source_datetime,
    priority_for_card,
    status_for_list,
    trello_object_created_at,
    validate_trello_document,
)
from app.models import (
    AuditEvent,
    DataRetentionPolicy,
    Demand,
    DemandCategory,
    DemandRevision,
    DemandTodoItem,
    DemandUpdate,
    Membership,
    MembershipStatus,
    TrelloCardLink,
    TrelloImportBatch,
    UserProfile,
    Workflow,
    WorkflowStage,
    utc_now,
)
from app.retention import archive_completed_demands, eligible_retention_count, get_or_create_policy

router = APIRouter(prefix="/governance", tags=["Governança"])


def require_admin(principal: Principal) -> None:
    if (
        principal.membership.status != MembershipStatus.ACTIVE
        or not principal.role
        or principal.role.code != "admin"
    ):
        raise ApiError(403, "admin_required", "Esta área é exclusiva para administradores.")


async def read_trello_upload(upload: UploadFile) -> tuple[bytes, dict[str, Any]]:
    raw = await upload.read()
    return raw, validate_trello_document(raw)


def source_indexes(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    lists = {str(item["id"]): item for item in document["lists"] if isinstance(item, dict)}
    labels = {
        str(item["id"]): item
        for item in document.get("labels", [])
        if isinstance(item, dict) and item.get("id")
    }
    checklists = {
        str(item["id"]): item
        for item in document.get("checklists", [])
        if isinstance(item, dict) and item.get("id")
    }
    members = {
        str(item["id"]): item
        for item in document.get("members", [])
        if isinstance(item, dict) and item.get("id")
    }
    return lists, labels, checklists, members


def active_profiles(db: Session, organization_id: uuid.UUID) -> list[UserProfile]:
    return list(
        db.scalars(
            select(UserProfile)
            .join(Membership, Membership.user_profile_id == UserProfile.id)
            .where(
                Membership.organization_id == organization_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
            .order_by(UserProfile.full_name)
        )
    )


def import_context(db: Session, principal: Principal) -> dict[str, Any]:
    organization_id = principal.membership.organization_id
    workflow = db.scalar(
        select(Workflow).where(
            Workflow.organization_id == organization_id,
            Workflow.active.is_(True),
            Workflow.is_default.is_(True),
        )
    )
    if not workflow:
        workflow = db.scalar(
            select(Workflow)
            .where(
                Workflow.organization_id == organization_id,
                Workflow.active.is_(True),
            )
            .order_by(Workflow.name)
        )
    if not workflow:
        raise ApiError(422, "workflow_required", "Cadastre um workflow ativo antes de importar.")
    version = ensure_workflow_version(db, organization_id, workflow.id, principal.profile.id)
    stages = list(
        db.scalars(
            select(WorkflowStage)
            .where(
                WorkflowStage.organization_id == organization_id,
                WorkflowStage.workflow_id == workflow.id,
                WorkflowStage.active.is_(True),
            )
            .order_by(WorkflowStage.position)
        )
    )
    if not stages:
        raise ApiError(
            422, "workflow_stage_required", "O workflow padrão precisa ter etapas ativas."
        )
    profiles = active_profiles(db, organization_id)
    categories = list(
        db.scalars(
            select(DemandCategory).where(
                DemandCategory.organization_id == organization_id,
                DemandCategory.active.is_(True),
            )
        )
    )
    return {
        "workflow": workflow,
        "version": version,
        "stages": stages,
        "profiles": profiles,
        "categories": categories,
    }


def stage_for_list(list_name: str, status: str, stages: list[WorkflowStage]) -> WorkflowStage:
    match = best_named_match(list_name, [(str(item.id), item.name) for item in stages])
    if match:
        return next(item for item in stages if str(item.id) == match)
    return stages[-1] if status == "COMPLETED" else stages[0]


def import_preview(
    db: Session,
    principal: Principal,
    raw: bytes,
    document: dict[str, Any],
) -> dict[str, Any]:
    organization_id = principal.membership.organization_id
    context = import_context(db, principal)
    lists, labels, checklists, members = source_indexes(document)
    board_id = str(document["id"])
    links = {
        item.card_id: item
        for item in db.scalars(
            select(TrelloCardLink).where(
                TrelloCardLink.organization_id == organization_id,
                TrelloCardLink.board_id == board_id,
            )
        )
    }
    new_cards = changed_cards = unchanged_cards = archived_cards = 0
    list_counts: dict[str, int] = {identifier: 0 for identifier in lists}
    for card in document["cards"]:
        list_counts[str(card["idList"])] = list_counts.get(str(card["idList"]), 0) + 1
        snapshot = card_snapshot(
            card, lists_by_id=lists, labels_by_id=labels, checklists_by_id=checklists
        )
        link = links.get(str(card["id"]))
        if not link:
            new_cards += 1
        elif link.source_hash == canonical_hash(snapshot):
            unchanged_cards += 1
        else:
            changed_cards += 1
        if (
            card.get("closed")
            or status_for_list(str(lists[str(card["idList"])].get("name", ""))) == "COMPLETED"
        ):
            archived_cards += 1
    profiles: list[UserProfile] = context["profiles"]
    member_mappings = []
    for member_id, member in members.items():
        name = str(member.get("fullName") or member.get("username") or member_id)
        matched = best_named_match(name, [(str(item.id), item.full_name) for item in profiles])
        member_mappings.append(
            {
                "sourceId": member_id,
                "sourceName": name,
                "profileId": matched,
                "profileName": next(
                    (item.full_name for item in profiles if str(item.id) == matched), None
                ),
            }
        )
    list_mappings = []
    for list_id, item in sorted(lists.items(), key=lambda pair: pair[1].get("pos", 0)):
        name = str(item.get("name", "Sem nome"))
        status = status_for_list(name)
        stage = stage_for_list(name, status, context["stages"])
        list_mappings.append(
            {
                "sourceId": list_id,
                "sourceName": name,
                "cards": list_counts.get(list_id, 0),
                "status": status,
                "stageId": str(stage.id),
                "stageName": stage.name,
            }
        )
    exact = db.scalar(
        select(TrelloImportBatch.id).where(
            TrelloImportBatch.organization_id == organization_id,
            TrelloImportBatch.document_hash == hashlib.sha256(raw).hexdigest(),
        )
    )
    warnings = []
    unmatched = [item["sourceName"] for item in member_mappings if not item["profileId"]]
    if unmatched:
        warnings.append(
            f"{len(unmatched)} membro(s) do Trello não correspondem automaticamente a usuários ativos."
        )
    if exact:
        warnings.append(
            "Este mesmo arquivo já possui um lote registrado e não poderá ser aplicado novamente."
        )
    return {
        "filename": "",
        "documentHash": hashlib.sha256(raw).hexdigest(),
        "alreadyImported": bool(exact),
        "board": {"id": board_id, "name": str(document["name"])},
        "counts": {
            "lists": len(lists),
            "cards": len(document["cards"]),
            "members": len(members),
            "labels": len(labels),
            "checklists": len(checklists),
            "new": new_cards,
            "changed": changed_cards,
            "unchanged": unchanged_cards,
            "sourceArchivedOrCompleted": archived_cards,
        },
        "listMappings": list_mappings,
        "memberMappings": member_mappings,
        "warnings": warnings,
    }


def allocate_public_ids(db: Session, count: int) -> list[str]:
    if count <= 0:
        return []
    year = utc_now().year
    last = db.execute(
        text(
            "INSERT INTO app.demand_counters (year, last_value) VALUES (:year, :count) "
            "ON CONFLICT (year) DO UPDATE SET last_value = demand_counters.last_value + :count "
            "RETURNING last_value"
        ),
        {"year": year, "count": count},
    ).scalar_one()
    return [f"DMD-{year}-{number:06d}" for number in range(last - count + 1, last + 1)]


def demand_state(demand: Demand) -> dict[str, Any]:
    fields = (
        "title",
        "description",
        "category_id",
        "current_assignee_id",
        "current_stage_id",
        "workflow_id",
        "workflow_version_id",
        "status",
        "priority",
        "deadline_at",
        "forecast_at",
        "archived_at",
        "deleted_at",
        "source",
        "revision",
        "updated_at",
    )
    return {field: jsonable_encoder(getattr(demand, field)) for field in fields}


def restore_demand_state(demand: Demand, values: dict[str, Any]) -> None:
    uuid_fields = {
        "id",
        "organization_id",
        "primary_company_id",
        "category_id",
        "current_assignee_id",
        "current_stage_id",
        "workflow_id",
        "workflow_version_id",
        "created_by",
    }
    date_fields = {
        "deadline_at",
        "forecast_at",
        "archived_at",
        "deleted_at",
        "created_at",
        "updated_at",
    }
    for field, value in values.items():
        if field in uuid_fields and value:
            value = uuid.UUID(str(value))
        elif field in date_fields and value:
            value = parse_source_datetime(value)
        if hasattr(demand, field):
            setattr(demand, field, value)


def mapped_profile(
    card: dict[str, Any], members: dict[str, Any], profiles: list[UserProfile]
) -> uuid.UUID | None:
    for member_id in card.get("idMembers", []):
        member = members.get(str(member_id), {})
        name = str(member.get("fullName") or member.get("username") or "")
        matched = best_named_match(name, [(str(item.id), item.full_name) for item in profiles])
        if matched:
            return uuid.UUID(matched)
    return None


def mapped_category(
    card: dict[str, Any], labels: dict[str, Any], categories: list[DemandCategory]
) -> uuid.UUID | None:
    for label_id in card.get("idLabels", []):
        label_name = str(labels.get(str(label_id), {}).get("name") or "")
        matched = best_named_match(label_name, [(str(item.id), item.name) for item in categories])
        if matched:
            return uuid.UUID(matched)
    return None


@router.post("/trello/validate", dependencies=[Depends(require_csrf)])
async def validate_trello(
    file: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_admin(principal)
    raw, document = await read_trello_upload(file)
    result = import_preview(db, principal, raw, document)
    result["filename"] = file.filename or "trello.json"
    return result


@router.post("/trello/apply", dependencies=[Depends(require_csrf)])
async def apply_trello(
    file: UploadFile = File(...),
    update_existing: bool = Form(default=False, alias="updateExisting"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_admin(principal)
    raw, document = await read_trello_upload(file)
    preview = import_preview(db, principal, raw, document)
    if preview["alreadyImported"]:
        raise ApiError(409, "trello_file_already_imported", "Este mesmo arquivo já foi importado.")
    organization_id = principal.membership.organization_id
    context = import_context(db, principal)
    lists, labels, checklists, members = source_indexes(document)
    board_id = str(document["id"])
    links = {
        item.card_id: item
        for item in db.scalars(
            select(TrelloCardLink).where(
                TrelloCardLink.organization_id == organization_id,
                TrelloCardLink.board_id == board_id,
            )
        )
    }
    new_total = sum(1 for card in document["cards"] if str(card["id"]) not in links)
    public_ids = iter(allocate_public_ids(db, new_total))
    now = utc_now()
    batch = TrelloImportBatch(
        id=uuid.uuid4(),
        organization_id=organization_id,
        uploaded_by=principal.profile.id,
        filename=(file.filename or "trello.json")[:255],
        board_id=board_id,
        board_name=str(document["name"])[:200],
        document_hash=hashlib.sha256(raw).hexdigest(),
        total_cards=len(document["cards"]),
        state="applied",
        applied_at=now,
    )
    db.add(batch)
    changes: list[dict[str, Any]] = []
    created = updated = unchanged = archived = 0
    try:
        for card in document["cards"]:
            card_id = str(card["id"])
            source = card_snapshot(
                card, lists_by_id=lists, labels_by_id=labels, checklists_by_id=checklists
            )
            source_hash = canonical_hash(source)
            link = links.get(card_id)
            if link and link.source_hash == source_hash:
                unchanged += 1
                continue
            if link and not update_existing:
                unchanged += 1
                continue
            list_name = str(lists[str(card["idList"])].get("name", ""))
            status = status_for_list(list_name)
            stage = stage_for_list(list_name, status, context["stages"])
            label_names = [
                str(labels.get(str(item), {}).get("name") or "")
                for item in card.get("idLabels", [])
            ]
            source_updated_at = parse_source_datetime(card.get("dateLastActivity"))
            assignee_id = mapped_profile(card, members, context["profiles"])
            category_id = mapped_category(card, labels, context["categories"])
            due = parse_source_datetime(card.get("due"))
            source_completed_old = status == "COMPLETED" and bool(
                source_updated_at and source_updated_at <= now - timedelta(days=60)
            )
            archived_at = now if card.get("closed") or source_completed_old else None
            if link:
                demand = db.get(Demand, link.demand_id)
                if not demand or demand.organization_id != organization_id:
                    raise ApiError(
                        409, "trello_link_invalid", f"Vínculo inválido para o cartão {card_id}."
                    )
                changes.append(
                    {
                        "kind": "updated",
                        "demandId": str(demand.id),
                        "cardId": card_id,
                        "before": demand_state(demand),
                        "previousLink": {
                            "sourceHash": link.source_hash,
                            "lastImportId": str(link.last_import_id),
                            "sourceUpdatedAt": jsonable_encoder(link.source_updated_at),
                        },
                    }
                )
                updated += 1
                demand.title = " ".join(str(card["name"]).split())[:300]
                demand.description = str(card.get("desc") or "") or None
                demand.category_id = category_id
                demand.current_assignee_id = assignee_id
                demand.current_stage_id = stage.id
                demand.workflow_id = context["workflow"].id
                demand.workflow_version_id = context["version"].id
                demand.status = status
                demand.priority = priority_for_card(card, list_name, label_names)
                demand.deadline_at = due
                demand.archived_at = archived_at
                demand.deleted_at = None
                demand.source = "trello_import"
                demand.revision += 1
                demand.updated_at = now
                link.last_import_id = batch.id
                link.source_hash = source_hash
                link.source_updated_at = source_updated_at
                link.updated_at = now
            else:
                demand = Demand(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    public_id=next(public_ids),
                    title=" ".join(str(card["name"]).split())[:300],
                    description=str(card.get("desc") or "") or None,
                    category_id=category_id,
                    current_assignee_id=assignee_id,
                    current_stage_id=stage.id,
                    workflow_id=context["workflow"].id,
                    workflow_version_id=context["version"].id,
                    status=status,
                    priority=priority_for_card(card, list_name, label_names),
                    deadline_at=due,
                    source="trello_import",
                    archived_at=archived_at,
                    created_by=principal.profile.id,
                    created_at=trello_object_created_at(card_id) or now,
                    updated_at=source_updated_at or now,
                )
                db.add(demand)
                link = TrelloCardLink(
                    organization_id=organization_id,
                    board_id=board_id,
                    card_id=card_id,
                    demand_id=demand.id,
                    last_import_id=batch.id,
                    source_hash=source_hash,
                    source_updated_at=source_updated_at,
                )
                db.add(link)
                changes.append({"kind": "created", "demandId": str(demand.id), "cardId": card_id})
                created += 1
                position = 0
                for checklist in source.get("checklists", []):
                    for check_item in checklist.get("checkItems", []):
                        position += 1
                        completed = check_item.get("state") == "complete"
                        db.add(
                            DemandTodoItem(
                                organization_id=organization_id,
                                demand_id=demand.id,
                                title=str(check_item.get("name") or "Item importado")[:240],
                                position=position,
                                completed=completed,
                                completed_by=principal.profile.id if completed else None,
                                completed_at=source_updated_at if completed else None,
                                created_by=principal.profile.id,
                            )
                        )
            if archived_at:
                archived += 1
            db.add(
                DemandUpdate(
                    demand_id=demand.id,
                    created_by=principal.profile.id,
                    kind="trello_import",
                    summary=f"Cartão importado do Trello: {document['name']}",
                    payload={"trello": source, "batchId": str(batch.id)},
                )
            )
        batch.created_cards = created
        batch.updated_cards = updated
        batch.unchanged_cards = unchanged
        batch.archived_cards = archived
        batch.summary_json = {"preview": preview, "updateExisting": update_existing}
        batch.changes_json = changes
        db.add(
            AuditEvent(
                organization_id=organization_id,
                actor_user_id=principal.profile.id,
                event_type="trello.import_applied",
                source="interface",
                metadata_json={
                    "batchId": str(batch.id),
                    "created": created,
                    "updated": updated,
                    "unchanged": unchanged,
                    "archived": archived,
                },
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            409,
            "trello_import_conflict",
            "A importação encontrou dados já vinculados. Valide o arquivo novamente.",
        ) from exc
    return {
        "batchId": str(batch.id),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "archived": archived,
    }


@router.get("/trello/batches")
def list_batches(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    require_admin(principal)
    items = db.scalars(
        select(TrelloImportBatch)
        .where(TrelloImportBatch.organization_id == principal.membership.organization_id)
        .order_by(TrelloImportBatch.created_at.desc())
        .limit(30)
    )
    return [
        {
            "id": str(item.id),
            "filename": item.filename,
            "boardName": item.board_name,
            "state": item.state,
            "totalCards": item.total_cards,
            "createdCards": item.created_cards,
            "updatedCards": item.updated_cards,
            "unchangedCards": item.unchanged_cards,
            "archivedCards": item.archived_cards,
            "createdAt": item.created_at,
            "appliedAt": item.applied_at,
            "revertedAt": item.reverted_at,
        }
        for item in items
    ]


@router.post("/trello/batches/{batch_id}/revert", dependencies=[Depends(require_csrf)])
def revert_batch(
    batch_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_admin(principal)
    organization_id = principal.membership.organization_id
    batch = db.scalar(
        select(TrelloImportBatch)
        .where(
            TrelloImportBatch.id == batch_id, TrelloImportBatch.organization_id == organization_id
        )
        .with_for_update()
    )
    if not batch:
        raise ApiError(404, "trello_batch_not_found", "Lote de importação não encontrado.")
    if batch.state == "reverted":
        raise ApiError(409, "trello_batch_already_reverted", "Este lote já foi revertido.")
    changes = list(batch.changes_json or [])
    for change in changes:
        link = db.scalar(
            select(TrelloCardLink).where(
                TrelloCardLink.organization_id == organization_id,
                TrelloCardLink.board_id == batch.board_id,
                TrelloCardLink.card_id == change["cardId"],
            )
        )
        if not link or link.last_import_id != batch.id:
            raise ApiError(
                409,
                "trello_revert_has_newer_changes",
                "Há alterações posteriores neste lote. Reverta primeiro a importação mais recente.",
            )
    restored = archived = 0
    now = utc_now()
    for change in reversed(changes):
        demand = db.get(Demand, uuid.UUID(change["demandId"]))
        link = db.scalar(
            select(TrelloCardLink).where(
                TrelloCardLink.organization_id == organization_id,
                TrelloCardLink.board_id == batch.board_id,
                TrelloCardLink.card_id == change["cardId"],
            )
        )
        if not demand or not link:
            continue
        if change["kind"] == "created":
            demand.deleted_at = now
            demand.archived_at = now
            demand.revision += 1
            demand.updated_at = now
            archived += 1
        else:
            restore_demand_state(demand, change["before"])
            previous = change["previousLink"]
            link.source_hash = previous["sourceHash"]
            link.last_import_id = uuid.UUID(previous["lastImportId"])
            link.source_updated_at = parse_source_datetime(previous.get("sourceUpdatedAt"))
            link.updated_at = now
            restored += 1
    batch.state = "reverted"
    batch.reverted_at = now
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=principal.profile.id,
            event_type="trello.import_reverted",
            source="interface",
            metadata_json={"batchId": str(batch.id), "restored": restored, "archived": archived},
        )
    )
    db.commit()
    return {"restored": restored, "archived": archived}


@router.get("/trello/export")
def export_trello(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> JSONResponse:
    require_admin(principal)
    organization_id = principal.membership.organization_id
    demands = list(
        db.scalars(
            select(Demand)
            .where(Demand.organization_id == organization_id, Demand.deleted_at.is_(None))
            .order_by(Demand.created_at)
        )
    )
    profiles = active_profiles(db, organization_id)
    categories = list(
        db.scalars(select(DemandCategory).where(DemandCategory.organization_id == organization_id))
    )
    status_lists = [
        ("WAITING_EXECUTION", "Aguardando execução"),
        ("IN_PROGRESS", "Em andamento"),
        ("WAITING_INFORMATION", "Aguardando informação"),
        ("WAITING_APPROVAL", "Aguardando aprovação"),
        ("BLOCKED", "Pausadas"),
        ("SCHEDULED", "Agendado"),
        ("COMPLETED", "Concluído"),
    ]
    list_ids = {
        status: hashlib.md5(status.encode(), usedforsecurity=False).hexdigest()[:24]
        for status, _ in status_lists
    }
    document = {
        "id": hashlib.md5(str(organization_id).encode(), usedforsecurity=False).hexdigest()[:24],
        "name": "Fluxo Marketing",
        "dateLastActivity": utc_now(),
        "lists": [
            {"id": list_ids[status], "name": name, "closed": False, "pos": (index + 1) * 16384}
            for index, (status, name) in enumerate(status_lists)
        ],
        "members": [
            {
                "id": str(item.id).replace("-", "")[:24],
                "fullName": item.full_name,
                "username": item.email.split("@")[0],
            }
            for item in profiles
        ],
        "labels": [
            {"id": str(item.id).replace("-", "")[:24], "name": item.name, "color": item.color}
            for item in categories
        ],
        "checklists": [],
        "cards": [
            {
                "id": str(item.id).replace("-", "")[:24],
                "name": item.title,
                "desc": item.description or "",
                "idList": list_ids.get(item.status, list_ids["WAITING_EXECUTION"]),
                "idMembers": [str(item.current_assignee_id).replace("-", "")[:24]]
                if item.current_assignee_id
                else [],
                "idLabels": [str(item.category_id).replace("-", "")[:24]]
                if item.category_id
                else [],
                "due": item.deadline_at,
                "dueComplete": item.status == "COMPLETED",
                "closed": bool(item.archived_at),
                "dateLastActivity": item.updated_at,
                "idChecklists": [],
                "attachments": [],
                "pos": index * 16384,
            }
            for index, item in enumerate(demands, 1)
        ],
        "actions": [],
        "exportedBy": "Fluxo Marketing",
    }
    filename = f"fluxo-marketing-trello-{utc_now().date().isoformat()}.json"
    return JSONResponse(
        content=jsonable_encoder(document),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/overview")
def governance_overview(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> dict[str, Any]:
    require_admin(principal)
    organization_id = principal.membership.organization_id
    events = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.organization_id == organization_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        )
    )
    actor_ids = {item.actor_user_id for item in events if item.actor_user_id}
    actors = (
        {
            item.id: item.full_name
            for item in db.scalars(select(UserProfile).where(UserProfile.id.in_(actor_ids)))
        }
        if actor_ids
        else {}
    )
    archived = list(
        db.scalars(
            select(Demand)
            .where(
                Demand.organization_id == organization_id,
                ((Demand.archived_at.is_not(None)) | (Demand.deleted_at.is_not(None))),
            )
            .order_by(func.coalesce(Demand.deleted_at, Demand.archived_at).desc())
            .limit(100)
        )
    )
    revisions = list(
        db.scalars(
            select(DemandRevision)
            .where(DemandRevision.organization_id == organization_id)
            .order_by(DemandRevision.created_at.desc())
            .limit(100)
        )
    )
    return {
        "events": [
            {
                "id": str(item.id),
                "eventType": item.event_type,
                "source": item.source,
                "actorName": actors.get(item.actor_user_id, "Sistema")
                if item.actor_user_id
                else "Sistema",
                "metadata": item.metadata_json,
                "createdAt": item.created_at,
            }
            for item in events
        ],
        "archivedDemands": [
            {
                "id": str(item.id),
                "publicId": item.public_id,
                "title": item.title,
                "status": item.status,
                "archivedAt": item.archived_at,
                "deletedAt": item.deleted_at,
            }
            for item in archived
        ],
        "revisions": [
            {
                "id": str(item.id),
                "demandId": str(item.demand_id),
                "revision": item.revision,
                "operation": item.operation,
                "title": item.snapshot.get("title", "Demanda"),
                "createdAt": item.created_at,
            }
            for item in revisions
        ],
    }


@router.post("/demands/{demand_id}/restore", dependencies=[Depends(require_csrf)])
def restore_demand(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_admin(principal)
    demand = db.scalar(
        select(Demand)
        .where(
            Demand.id == demand_id, Demand.organization_id == principal.membership.organization_id
        )
        .with_for_update()
    )
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    demand.archived_at = None
    demand.deleted_at = None
    demand.revision += 1
    demand.updated_at = utc_now()
    db.add(
        AuditEvent(
            organization_id=demand.organization_id,
            actor_user_id=principal.profile.id,
            event_type="demand.restored",
            source="interface",
            metadata_json={"demandId": str(demand.id)},
        )
    )
    db.commit()
    return {"id": str(demand.id), "restored": True}


@router.post("/revisions/{revision_id}/restore", dependencies=[Depends(require_csrf)])
def restore_revision(
    revision_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_admin(principal)
    revision = db.scalar(
        select(DemandRevision).where(
            DemandRevision.id == revision_id,
            DemandRevision.organization_id == principal.membership.organization_id,
        )
    )
    if not revision:
        raise ApiError(404, "revision_not_found", "Versão da demanda não encontrada.")
    demand = db.get(Demand, revision.demand_id)
    if demand and demand.organization_id != principal.membership.organization_id:
        raise ApiError(404, "demand_not_found", "A demanda desta versão não está disponível.")
    if not demand:
        demand = Demand()
        db.add(demand)
    restore_demand_state(demand, revision.snapshot)
    demand.revision = max(demand.revision, revision.revision) + 1
    demand.updated_at = utc_now()
    db.add(
        AuditEvent(
            organization_id=demand.organization_id,
            actor_user_id=principal.profile.id,
            event_type="demand.revision_restored",
            source="interface",
            metadata_json={"demandId": str(demand.id), "revisionId": str(revision.id)},
        )
    )
    db.commit()
    return {"id": str(demand.id), "restoredRevision": revision.revision}


def policy_output(db: Session, policy: DataRetentionPolicy) -> dict[str, Any]:
    return {
        "automaticEnabled": policy.automatic_enabled,
        "intervalDays": policy.interval_days,
        "completedAfterDays": policy.completed_after_days,
        "lastRunAt": policy.last_run_at,
        "eligibleCompleted": eligible_retention_count(db, policy),
        "permanentDeletion": False,
    }


@router.get("/retention")
def get_retention(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> dict[str, Any]:
    require_admin(principal)
    policy = get_or_create_policy(db, principal.membership.organization_id)
    db.commit()
    return policy_output(db, policy)


@router.put("/retention", dependencies=[Depends(require_csrf)])
def update_retention(
    payload: dict[str, Any],
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_admin(principal)
    interval = int(payload.get("intervalDays", 60))
    completed = int(payload.get("completedAfterDays", 60))
    if not 30 <= interval <= 365 or not 30 <= completed <= 3650:
        raise ApiError(
            422,
            "retention_invalid",
            "Use entre 30 e 365 dias para o ciclo e ao menos 30 dias para demandas concluídas.",
        )
    policy = get_or_create_policy(db, principal.membership.organization_id)
    policy.automatic_enabled = bool(payload.get("automaticEnabled", True))
    policy.interval_days = interval
    policy.completed_after_days = completed
    policy.updated_by = principal.profile.id
    policy.updated_at = utc_now()
    db.commit()
    return policy_output(db, policy)


@router.post("/retention/run", dependencies=[Depends(require_csrf)])
def run_retention(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> dict[str, Any]:
    require_admin(principal)
    policy = get_or_create_policy(db, principal.membership.organization_id)
    count = archive_completed_demands(db, policy, actor_id=principal.profile.id, source="interface")
    db.commit()
    return {"archived": count, "permanentDeletion": False, "policy": policy_output(db, policy)}
