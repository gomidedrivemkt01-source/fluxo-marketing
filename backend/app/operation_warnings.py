"""Ciência explícita de pendências de negócio, vinculada à alteração e à revisão atual."""

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.service import Principal
from app.models import AuditEvent, Demand, DemandUpdate


class WarningAcknowledgement(BaseModel):
    acknowledged_warnings: list[str] = Field(
        default_factory=list, alias="acknowledgedWarnings", max_length=200
    )


def confirm_warnings(
    db: Session,
    principal: Principal,
    demand: Demand,
    warnings: list[dict[str, str]],
    acknowledged: list[str],
    *,
    action: str,
) -> None:
    if not warnings:
        return
    if not {item["code"] for item in warnings}.issubset(set(acknowledged)):
        raise ApiError(
            409,
            "acknowledgement_required",
            "Confira as pendências antes de continuar.",
            {
                "warnings": warnings,
                "fieldErrors": warnings,
                "canProceed": True,
            },
        )
    details = {
        "action": action,
        "warnings": warnings,
        "demandId": str(demand.id),
        "revision": demand.revision,
    }
    db.add(
        DemandUpdate(
            demand_id=demand.id,
            created_by=principal.profile.id,
            kind="WARNING_ACKNOWLEDGED",
            summary="Seguiu mesmo assim, com ciência: "
            + "; ".join(item["message"] for item in warnings),
            payload=details,
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type="DEMAND_WARNING_ACKNOWLEDGED",
            metadata_json=details,
        )
    )
