"""Evidence-based stage participation, final deliveries and operational analytics.

Assignment, timer activity and the person clicking a button do not constitute a
delivery. A real forward handoff is attributed to the recorded stage assignee.
Confirmed credit is distinct per person/card and dated by final completion.
"""

import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models import (
    Company,
    Demand,
    DemandCategory,
    DemandStageVisit,
    DemandUpdate,
    TimeEntry,
    UserProfile,
    Workflow,
    WorkflowStage,
    WorkflowVersion,
)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (index - low), 1)


def version_positions(version: WorkflowVersion | None) -> dict[str, int]:
    return {
        str(item["id"]): int(item.get("position", index))
        for index, item in enumerate((version.definition if version else {}).get("stages", []))
        if isinstance(item, dict) and item.get("id")
    }


def stage_exit(
    visit: DemandStageVisit,
    following: DemandStageVisit | None,
    events: list[DemandUpdate],
    versions: dict[uuid.UUID, WorkflowVersion],
) -> str | None:
    snapshot = visit.acceptance_snapshot or {}
    if not visit.left_at or (visit.inferred and not snapshot.get("exitRecordedAt")):
        return None
    action = snapshot.get("exitAction")
    target = snapshot.get("exitStageId")
    if (
        not action
        and following
        and not following.inferred
        and abs((following.entered_at - visit.left_at).total_seconds()) <= 1
        and str((following.acceptance_snapshot or {}).get("fromStageId"))
        == str(visit.workflow_stage_id)
    ):
        action = following.action.upper()
        target = str(following.workflow_stage_id)
    positions = version_positions(versions.get(visit.workflow_version_id))
    terminal = bool(positions) and positions.get(str(visit.workflow_stage_id)) == max(
        positions.values()
    )
    if (
        not action
        and terminal
        and any(
            event.kind == "DEMAND_COMPLETED"
            and (event.payload or {}).get("action") == "advance"
            and str((event.payload or {}).get("fromStageId")) == str(visit.workflow_stage_id)
            and 0 <= (event.created_at - visit.left_at).total_seconds() <= 60
            for event in events
        )
    ):
        action = "COMPLETE"
    if action == "MANUAL":
        if (
            target in positions
            and str(visit.workflow_stage_id) in positions
            and positions[target] > positions[str(visit.workflow_stage_id)]
        ):
            return "ADVANCE"
        return None
    if action == "COMPLETE" and not terminal:
        return None
    return str(action) if action else None


def build_analytics(
    *,
    demands: list[Demand],
    visits: list[DemandStageVisit],
    events: list[DemandUpdate],
    entries: list[TimeEntry],
    versions: dict[uuid.UUID, WorkflowVersion],
    profiles: dict[uuid.UUID, UserProfile],
    stages: dict[uuid.UUID, WorkflowStage],
    workflows: dict[uuid.UUID, Workflow],
    companies: dict[uuid.UUID, Company],
    categories: dict[uuid.UUID, DemandCategory],
    scope_profile_id: uuid.UUID | None,
    started_at: datetime,
    ended_at: datetime,
    now: datetime,
    timezone_name: str,
    warning_days: int,
) -> dict[str, Any]:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("America/Sao_Paulo")
    span = max(1, (ended_at.astimezone(zone).date() - started_at.astimezone(zone).date()).days + 1)
    granularity = "day" if span <= 45 else "week" if span <= 180 else "month"

    def bucket(value: datetime) -> str:
        day = value.astimezone(zone).date()
        if granularity == "week":
            day -= timedelta(days=day.weekday())
        if granularity == "month":
            day = day.replace(day=1)
        return day.isoformat()

    series: dict[str, dict[str, Any]] = {}
    cursor = started_at.astimezone(zone).date()
    while cursor <= ended_at.astimezone(zone).date():
        key = bucket(datetime.combine(cursor, datetime.min.time(), tzinfo=zone))
        series.setdefault(
            key,
            {
                "date": key,
                "cardsCompleted": 0,
                "confirmedContributions": 0,
                "stageAdvances": 0,
                "trackedMinutes": 0,
            },
        )
        cursor += timedelta(days=1)
    by_card: dict[uuid.UUID, list[DemandStageVisit]] = defaultdict(list)
    card_events: dict[uuid.UUID, list[DemandUpdate]] = defaultdict(list)
    for visit in visits:
        by_card[visit.demand_id].append(visit)
    for event in events:
        card_events[event.demand_id].append(event)
    cards = {card.id: card for card in demands}
    actions = {}
    final_dates: dict[uuid.UUID, datetime] = {}
    verified_final_dates: dict[uuid.UUID, datetime] = {}
    final_visits: dict[uuid.UUID, DemandStageVisit] = {}
    for card in demands:
        sequence = sorted(by_card[card.id], key=lambda item: item.visit_number)
        history = card_events[card.id]
        for index, visit in enumerate(sequence):
            actions[visit.id] = stage_exit(
                visit, sequence[index + 1] if index + 1 < len(sequence) else None, history, versions
            )
        if card.status != "COMPLETED":
            continue
        completions = [item.created_at for item in history if item.kind == "DEMAND_COMPLETED"]
        terminals = [item for item in sequence if actions.get(item.id) == "COMPLETE"]
        latest = (
            max(completions)
            if completions
            else max((item.left_at for item in terminals if item.left_at is not None), default=None)
        )
        if latest is None:
            continue
        final_dates[card.id] = latest
        terminal = next(
            (
                item
                for item in reversed(terminals)
                if item.left_at and 0 <= (latest - item.left_at).total_seconds() <= 60
            ),
            None,
        )
        if terminal:
            verified_final_dates[card.id] = latest
            final_visits[card.id] = terminal

    people: dict[uuid.UUID, dict[str, Any]] = {}

    def person(identifier: uuid.UUID) -> dict[str, Any]:
        if identifier not in people:
            profile = profiles.get(identifier)
            people[identifier] = {
                "profileId": str(identifier),
                "name": profile.full_name if profile else "Pessoa do histórico",
                "confirmed": set(),
                "pending": set(),
                "advanced": set(),
                "stageAdvances": 0,
                "activeCards": set(),
                "overdueCards": set(),
                "trackedMinutes": 0,
            }
        return people[identifier]

    def allowed(identifier: uuid.UUID | None) -> bool:
        return bool(identifier) and (scope_profile_id is None or identifier == scope_profile_id)

    stage_groups: dict[uuid.UUID, dict[str, Any]] = {}
    advanced_cards = set()
    inferred_visits = sum(
        bool(item.inferred)
        for item in visits
        if scope_profile_id is None or item.assignee_id == scope_profile_id
    )
    raw_advances = 0
    confirmed_pairs = set()
    for visit in visits:
        if not allowed(visit.assignee_id):
            continue
        action = actions.get(visit.id)
        if action in {"ADVANCE", "COMPLETE"}:
            assert visit.assignee_id is not None and visit.left_at is not None
            row = person(visit.assignee_id)
            final = verified_final_dates.get(visit.demand_id)
            if final and visit.left_at <= final and started_at <= final <= ended_at:
                pair = (visit.demand_id, visit.assignee_id)
                if pair not in confirmed_pairs:
                    confirmed_pairs.add(pair)
                    row["confirmed"].add(visit.demand_id)
                    series[bucket(final)]["confirmedContributions"] += 1
            if started_at <= visit.left_at <= ended_at:
                row["advanced"].add(visit.demand_id)
                row["stageAdvances"] += 1
                advanced_cards.add(visit.demand_id)
                raw_advances += 1
                series[bucket(visit.left_at)]["stageAdvances"] += 1
                if final is None:
                    row["pending"].add(visit.demand_id)
        # Permanence and SLA are measured only on closed, recorded forward exits.
        if (
            visit.inferred
            or action not in {"ADVANCE", "COMPLETE", "RETURN"}
            or not visit.left_at
            or not (started_at <= visit.left_at <= ended_at)
        ):
            continue
        snapshot = visit.acceptance_snapshot or {}
        stage = stages.get(visit.workflow_stage_id)
        version = versions.get(visit.workflow_version_id)
        workflow = workflows.get(version.workflow_id) if version else None
        group = stage_groups.setdefault(
            visit.workflow_stage_id,
            {
                "id": str(visit.workflow_stage_id),
                "name": snapshot.get("stageName")
                or (stage.name if stage else "Etapa do histórico"),
                "workflowName": workflow.name if workflow else "Workflow do histórico",
                "hours": [],
                "returns": 0,
                "withinSla": 0,
                "measuredSla": 0,
            },
        )
        group["returns"] += int(action == "RETURN")
        if action in {"ADVANCE", "COMPLETE"}:
            hours = max(0, (visit.left_at - visit.entered_at).total_seconds() / 3600)
            group["hours"].append(hours)
            sla = snapshot.get("slaHours")
            if isinstance(sla, (int, float)) and sla > 0:
                group["measuredSla"] += 1
                group["withinSla"] += int(hours <= sla)

    completed_in_period = {
        identifier for identifier, at in final_dates.items() if started_at <= at <= ended_at
    }
    # Person reports count only completed cards related to their real contribution,
    # not the colleague who owns the last stage or the actor who clicked completion.
    if scope_profile_id is not None:
        related = {
            visit.demand_id
            for visit in visits
            if visit.assignee_id == scope_profile_id
            and (not visit.inferred or (visit.acceptance_snapshot or {}).get("exitRecordedAt"))
        }
        completed_in_period &= related
    for identifier in completed_in_period:
        series[bucket(final_dates[identifier])]["cardsCompleted"] += 1
    active = [
        card
        for card in demands
        if card.status != "COMPLETED" and not card.archived_at and not card.deleted_at
    ]
    own_active = [
        card
        for card in active
        if scope_profile_id is None or card.current_assignee_id == scope_profile_id
    ]
    for card in own_active:
        if card.current_assignee_id is not None and allowed(card.current_assignee_id):
            row = person(card.current_assignee_id)
            row["activeCards"].add(card.id)
            if card.deadline_at and card.deadline_at < now:
                row["overdueCards"].add(card.id)
    time_allocation: dict[str, dict[str, Any]] = {}
    tracked_minutes = 0
    for entry in entries:
        if not allowed(entry.user_profile_id) or entry.state != "COMPLETED" or entry.deleted_at:
            continue
        at = entry.ended_at or entry.started_at
        if not started_at <= at <= ended_at:
            continue
        minutes = entry.duration_minutes or 0
        tracked_minutes += minutes
        person(entry.user_profile_id)["trackedMinutes"] += minutes
        series[bucket(at)]["trackedMinutes"] += minutes
        entry_card = cards.get(entry.demand_id)
        category = (
            categories.get(entry_card.category_id)
            if entry_card and entry_card.category_id
            else None
        )
        key = str(category.id) if category else "unclassified"
        allocation = time_allocation.setdefault(
            key,
            {
                "id": key,
                "label": category.name if category else "Sem categoria",
                "color": category.color if category else None,
                "minutes": 0,
            },
        )
        allocation["minutes"] += minutes
    risks: dict[str, list[Demand]] = {"overdue": [], "dueSoon": [], "later": [], "undated": []}
    for card in own_active:
        key = (
            "undated"
            if not card.deadline_at
            else "overdue"
            if card.deadline_at < now
            else "dueSoon"
            if card.deadline_at < now + timedelta(days=warning_days)
            else "later"
        )
        risks[key].append(card)
    attention = []
    for key in ("overdue", "dueSoon", "undated"):
        for card in sorted(
            risks[key], key=lambda item: item.deadline_at or datetime.max.replace(tzinfo=now.tzinfo)
        ):
            company = companies.get(card.primary_company_id) if card.primary_company_id else None
            attention.append(
                {
                    "id": str(card.id),
                    "publicId": card.public_id,
                    "title": card.title,
                    "companyName": company.name if company else None,
                    "deadlineAt": card.deadline_at,
                    "reason": {
                        "overdue": "Prazo vencido",
                        "dueSoon": f"Menos de {warning_days} dias",
                        "undated": "Sem prazo",
                    }[key],
                }
            )
    person_rows = []
    for row in people.values():
        person_rows.append(
            {
                **{key: value for key, value in row.items() if not isinstance(value, set)},
                "confirmedDeliveries": len(row["confirmed"]),
                "awaitingFinal": len(row["pending"]),
                "advancedCards": len(row["advanced"]),
                "activeCards": len(row["activeCards"]),
                "overdueCards": len(row["overdueCards"]),
            }
        )
    person_rows.sort(key=lambda row: row["name"].casefold())
    stage_rows = [
        {
            "id": row["id"],
            "name": row["name"],
            "workflowName": row["workflowName"],
            "completedVisits": len(row["hours"]),
            "medianHours": percentile(row["hours"], 0.5),
            "p90Hours": percentile(row["hours"], 0.9),
            "returns": row["returns"],
            "slaRate": round(row["withinSla"] / row["measuredSla"] * 100)
            if row["measuredSla"]
            else None,
            "measuredSla": row["measuredSla"],
        }
        for row in stage_groups.values()
    ]
    stage_rows.sort(key=lambda row: -(row["p90Hours"] or 0))
    cycle_hours = [
        (final_dates[identifier] - cards[identifier].created_at).total_seconds() / 3600
        for identifier in completed_in_period
        if final_dates[identifier] >= cards[identifier].created_at
    ]
    known_deadlines = [
        (at, (final_visits[identifier].acceptance_snapshot or {}).get("demandDeadlineAt"))
        for identifier, at in verified_final_dates.items()
        if identifier in completed_in_period
    ]
    deadline_results = []
    for at, deadline in known_deadlines:
        if deadline:
            try:
                deadline_results.append(
                    at <= datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
                )
            except (ValueError, TypeError):
                pass
    return {
        "summary": {
            "confirmedDeliveries": len(confirmed_pairs),
            "awaitingFinal": sum(row["awaitingFinal"] for row in person_rows),
            "completedCards": len(completed_in_period),
            "advancedCards": len(advanced_cards),
            "stageAdvances": raw_advances,
            "activeCards": len(own_active),
            "overdueCards": len(risks["overdue"]),
            "dueSoon": len(risks["dueSoon"]),
            "trackedMinutes": tracked_minutes,
            "medianCycleHours": percentile(cycle_hours, 0.5),
            "p90CycleHours": percentile(cycle_hours, 0.9),
            "onTimeRate": round(sum(deadline_results) / len(deadline_results) * 100)
            if deadline_results
            else None,
            "measuredDeadlines": len(deadline_results),
        },
        "people": person_rows,
        "trend": list(series.values()),
        "granularity": granularity,
        "stages": stage_rows,
        "timeAllocation": sorted(time_allocation.values(), key=lambda row: -row["minutes"]),
        "deadlineRisk": [{"id": key, "count": len(value)} for key, value in risks.items()],
        "attention": attention[:30],
        "quality": {
            "inferredVisitsExcluded": inferred_visits,
            "completedWithoutFinalEvidence": sum(
                card.status == "COMPLETED" and card.id not in verified_final_dates
                for card in demands
            ),
            "undatedActive": len(risks["undated"]),
            "unassignedActive": sum(card.current_assignee_id is None for card in own_active),
            "verifiedCompletedCards": len(verified_final_dates),
        },
    }
