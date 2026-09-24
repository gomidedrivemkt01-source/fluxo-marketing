import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.api.access import require_any_permission, require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import AuditEvent, Company, Demand, DemandCategory, DemandUpdate, utc_now

router = APIRouter(prefix="/demands", tags=["Demandas"])


class DemandCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    company_id: uuid.UUID | None = Field(default=None, alias="companyId")
    category_id: uuid.UUID | None = Field(default=None, alias="categoryId")
    priority: str = Field(default="NORMAL", pattern=r"^(LOW|NORMAL|HIGH|URGENT)$")
    deadline_at: datetime | None = Field(default=None, alias="deadlineAt")


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
    status: str
    priority: str
    deadline_at: datetime | None = Field(alias="deadlineAt")
    forecast_at: datetime | None = Field(alias="forecastAt")
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


class DemandUpdateOut(BaseModel):
    id: uuid.UUID
    kind: str
    summary: str
    payload: dict[str, object]
    created_at: datetime = Field(alias="createdAt")


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
    source: str = "interface",
) -> Demand:
    demand = Demand(
        organization_id=principal.membership.organization_id,
        public_id=next_public_id(db),
        title=" ".join(title.split()),
        description=description,
        primary_company_id=company_id,
        category_id=category_id,
        priority=priority,
        deadline_at=deadline_at,
        source=source,
        created_by=principal.profile.id,
    )
    db.add(demand)
    db.flush()
    return demand


def demand_out(db: Session, demand: Demand) -> DemandOut:
    company = db.get(Company, demand.primary_company_id) if demand.primary_company_id else None
    category = db.get(DemandCategory, demand.category_id) if demand.category_id else None
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
        status=demand.status,
        priority=demand.priority,
        deadlineAt=demand.deadline_at,
        forecastAt=demand.forecast_at,
        revision=demand.revision,
        createdAt=demand.created_at,
    )


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
    demand = create_demand_record(
        db,
        principal,
        title=payload.title,
        description=payload.description,
        company_id=payload.company_id,
        category_id=payload.category_id,
        priority=payload.priority,
        deadline_at=payload.deadline_at,
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
    before = {
        "title": demand.title,
        "status": demand.status,
        "priority": demand.priority,
        "revision": demand.revision,
    }
    demand.title = " ".join(payload.title.split())
    demand.description = payload.description
    demand.primary_company_id = payload.company_id
    demand.category_id = payload.category_id
    demand.priority = payload.priority
    demand.status = payload.status
    demand.deadline_at = payload.deadline_at
    demand.revision += 1
    demand.updated_at = utc_now()
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
