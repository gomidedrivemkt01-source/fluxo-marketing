"""Arquivamento periódico e reversível de demandas concluídas."""

import asyncio
import uuid
from contextlib import suppress
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AuditEvent, DataRetentionPolicy, Demand, Organization, utc_now


def get_or_create_policy(db: Session, organization_id: uuid.UUID) -> DataRetentionPolicy:
    policy = db.get(DataRetentionPolicy, organization_id)
    if policy:
        return policy
    policy = DataRetentionPolicy(organization_id=organization_id)
    db.add(policy)
    db.flush()
    return policy


def eligible_retention_count(db: Session, policy: DataRetentionPolicy) -> int:
    cutoff = utc_now() - timedelta(days=policy.completed_after_days)
    return len(
        list(
            db.scalars(
                select(Demand.id).where(
                    Demand.organization_id == policy.organization_id,
                    Demand.status == "COMPLETED",
                    Demand.archived_at.is_(None),
                    Demand.deleted_at.is_(None),
                    Demand.updated_at <= cutoff,
                )
            )
        )
    )


def archive_completed_demands(
    db: Session,
    policy: DataRetentionPolicy,
    *,
    actor_id: uuid.UUID | None,
    source: str,
) -> int:
    now = utc_now()
    cutoff = now - timedelta(days=policy.completed_after_days)
    eligible_ids = list(
        db.scalars(
            select(Demand.id).where(
                Demand.organization_id == policy.organization_id,
                Demand.status == "COMPLETED",
                Demand.archived_at.is_(None),
                Demand.deleted_at.is_(None),
                Demand.updated_at <= cutoff,
            )
        )
    )
    if eligible_ids:
        db.execute(
            update(Demand)
            .where(Demand.id.in_(eligible_ids))
            .values(archived_at=now, updated_at=now, revision=Demand.revision + 1)
        )
    count = len(eligible_ids)
    policy.last_run_at = now
    policy.updated_at = now
    db.add(
        AuditEvent(
            organization_id=policy.organization_id,
            actor_user_id=actor_id,
            event_type="retention.completed_demands_archived",
            source=source,
            metadata_json={
                "count": count,
                "completedAfterDays": policy.completed_after_days,
                "permanentDeletion": False,
            },
        )
    )
    return count


def run_due_retention() -> None:
    with SessionLocal() as db:
        now = utc_now()
        for organization_id in db.scalars(
            select(Organization.id).where(Organization.active.is_(True))
        ):
            policy = get_or_create_policy(db, organization_id)
            if not policy.automatic_enabled:
                continue
            if policy.last_run_at and policy.last_run_at > now - timedelta(
                days=policy.interval_days
            ):
                continue
            archive_completed_demands(db, policy, actor_id=None, source="scheduler")
        db.commit()


async def retention_loop() -> None:
    while True:
        with suppress(Exception):
            await asyncio.to_thread(run_due_retention)
        await asyncio.sleep(6 * 60 * 60)
