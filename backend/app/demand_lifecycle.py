"""Completion archives operational cards without deleting their performance history."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.models import AuditEvent, Demand, DemandUpdate, TimeEntry, utc_now


def set_demand_status(
    db: Session,
    demand: Demand,
    status: str,
    *,
    actor_id: uuid.UUID,
    source: str,
) -> None:
    previous = demand.status
    if status == "COMPLETED" and previous != "COMPLETED":
        active_timer = db.scalar(
            select(TimeEntry.id).where(
                TimeEntry.demand_id == demand.id,
                TimeEntry.organization_id == demand.organization_id,
                TimeEntry.deleted_at.is_(None),
                TimeEntry.state.in_(("RUNNING", "PAUSED")),
            )
        )
        if active_timer:
            raise ApiError(
                409,
                "active_timer_requires_closure",
                "Finalize o timer aberto nesta demanda antes de concluí-la e arquivá-la.",
            )
    demand.status = status
    if status == "COMPLETED" and demand.archived_at is None:
        demand.archived_at = utc_now()
        kind = "DEMAND_ARCHIVED"
        summary = "Demanda arquivada automaticamente após a conclusão."
    elif previous == "COMPLETED" and status != "COMPLETED":
        demand.archived_at = None
        kind = "DEMAND_REOPENED"
        summary = "Demanda reaberta e devolvida às áreas de trabalho."
    else:
        return
    # The caller owns the revision, transaction and ordinary status/stage event.
    # Time entries, comments, files and completed stage visits remain untouched.
    payload = {"previousStatus": previous, "status": status, "automatic": True}
    if status == "COMPLETED" and previous != "COMPLETED" and source != "workflow":
        db.add(
            DemandUpdate(
                demand_id=demand.id,
                created_by=actor_id,
                kind="DEMAND_COMPLETED",
                summary="Demanda concluída.",
                payload=payload,
            )
        )
    db.add(
        DemandUpdate(
            demand_id=demand.id,
            created_by=actor_id,
            kind=kind,
            summary=summary,
            payload=payload,
        )
    )
    db.add(
        AuditEvent(
            organization_id=demand.organization_id,
            actor_user_id=actor_id,
            event_type=kind,
            source=source,
            metadata_json={"demandId": str(demand.id), **payload},
        )
    )
