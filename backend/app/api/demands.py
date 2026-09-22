import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.api.access import require_permission
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.database import get_db
from app.models import AuditEvent, Demand, DemandUpdate, utc_now

router = APIRouter(prefix="/demands", tags=["Demandas"])


class DemandCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    company_id: uuid.UUID | None = Field(default=None, alias="companyId")
    category_id: uuid.UUID | None = Field(default=None, alias="categoryId")
    priority: str = Field(default="NORMAL", pattern=r"^(LOW|NORMAL|HIGH|URGENT)$")


class DemandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    public_id: str = Field(alias="publicId")
    title: str
    description: str | None
    status: str
    priority: str
    deadline_at: datetime | None = Field(alias="deadlineAt")
    forecast_at: datetime | None = Field(alias="forecastAt")
    revision: int
    created_at: datetime = Field(alias="createdAt")


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
        source=source,
        created_by=principal.profile.id,
    )
    db.add(demand)
    db.flush()
    return demand


@router.get("", response_model=list[DemandOut])
def list_demands(
    q: str | None = Query(default=None, max_length=300),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[Demand]:
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
    return list(db.scalars(statement.order_by(Demand.updated_at.desc()).limit(50)))


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
) -> Demand:
    require_permission(principal, "demands:write")
    demand = create_demand_record(
        db,
        principal,
        title=payload.title,
        description=payload.description,
        company_id=payload.company_id,
        category_id=payload.category_id,
        priority=payload.priority,
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
    return demand


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
        from app.api.errors import ApiError

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
