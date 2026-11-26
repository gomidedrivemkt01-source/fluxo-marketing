"""Immediate, private performance from recorded activity and workflow evidence."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from app.analytics import stage_exit, version_positions
from app.models import Demand, DemandStageVisit, DemandUpdate, TimeEntry, WorkflowVersion

TIMER_KINDS = {"TIMER_STARTED", "TIMER_RESUMED", "TIMER_PAUSED", "TIMER_STOPPED"}
MIN_BASELINE_CARDS = 8


def union_intervals(values: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    result: list[tuple[datetime, datetime]] = []
    for start, end in sorted(values):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def timer_event_at(event: DemandUpdate) -> datetime:
    try:
        value = (event.payload or {}).get("at")
        if value:
            exact = datetime.fromisoformat(value)
            if exact.tzinfo is not None:
                return exact
    except (ValueError, TypeError):
        pass
    return event.created_at


def timer_spans(
    entry: TimeEntry, events: list[DemandUpdate], now: datetime
) -> list[tuple[datetime, datetime, bool]]:
    """Only recorded START/RESUME to PAUSE/STOP pairs; never fill a pause."""
    spans = []
    opened = None
    for event in sorted(events, key=lambda value: (value.created_at, str(value.id))):
        if event.kind not in TIMER_KINDS:
            continue
        at = timer_event_at(event)
        if at > now:
            continue
        if event.kind in {"TIMER_STARTED", "TIMER_RESUMED"}:
            if opened is None:
                opened = at
        elif opened is not None:
            if at > opened:
                spans.append((opened, at, False))
            opened = None
    if opened is not None:
        if entry.state == "RUNNING":
            if now > opened:
                spans.append((opened, now, True))
        elif entry.ended_at and entry.ended_at >= opened:
            spans.append((opened, min(entry.ended_at, now), False))
    return spans


def build_personal_performance(
    *,
    profile_id: uuid.UUID,
    cards: list[Demand],
    visits: list[DemandStageVisit],
    events: list[DemandUpdate],
    entries: list[TimeEntry],
    versions: dict[uuid.UUID, WorkflowVersion],
    start: datetime,
    end: datetime,
    now: datetime,
    zone: ZoneInfo,
    gap_minutes: int = 90,
    day_start: time = time(8),
    day_end: time = time(18),
) -> dict[str, Any]:
    stop = min(end, now)
    by_card: dict[uuid.UUID, list[DemandStageVisit]] = defaultdict(list)
    completion_events: dict[uuid.UUID, list[DemandUpdate]] = defaultdict(list)
    entry_events: dict[str, list[DemandUpdate]] = defaultdict(list)
    card_map = {card.id: card for card in cards}
    for visit in visits:
        by_card[visit.demand_id].append(visit)
    for event in events:
        if event.kind == "DEMAND_COMPLETED":
            completion_events[event.demand_id].append(event)
        if (event.payload or {}).get("timeEntryId"):
            entry_events[str(event.payload["timeEntryId"])].append(event)
    actions: dict[uuid.UUID, str | None] = {}
    finals: dict[uuid.UUID, datetime] = {}
    for card in cards:
        sequence = sorted(by_card[card.id], key=lambda value: value.visit_number)
        by_card[card.id] = sequence
        for index, visit in enumerate(sequence):
            actions[visit.id] = stage_exit(
                visit,
                sequence[index + 1] if index + 1 < len(sequence) else None,
                completion_events[card.id],
                versions,
            )
        if card.status == "COMPLETED":
            terminals = [v.left_at for v in sequence if v.left_at and actions[v.id] == "COMPLETE"]
            completed = [e.created_at for e in completion_events[card.id]]
            last = max(completed) if completed else max(terminals, default=None)
            if (
                last
                and any(0 <= (last - at).total_seconds() <= 60 for at in terminals)
                and last <= now
            ):
                finals[card.id] = last

    def inside(at: datetime) -> bool:
        return start <= at < end and at <= now

    def card_info(identifier: uuid.UUID) -> dict[str, Any]:
        card = card_map[identifier]
        return {
            "id": str(card.id),
            "title": card.title,
            "publicId": card.public_id,
            "canOpen": card.deleted_at is None,
        }

    days: dict[str, dict[str, Any]] = {}
    cursor = start.astimezone(zone).date()
    while cursor < end.astimezone(zone).date():
        days[cursor.isoformat()] = {
            "date": cursor.isoformat(),
            "recordedMinutes": 0.0,
            "pendingMinutes": 0.0,
            "coverageMinutes": 0.0,
            "timerStarts": 0,
            "timerResumes": 0,
            "stageAdvances": 0,
            "deliveredCards": set(),
            "returns": 0,
        }
        cursor += timedelta(days=1)
    segments: list[dict[str, Any]] = []
    slices: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    unlocated_minutes = 0.0
    uncertain_entries = 0
    unlocated_pending_minutes = 0.0
    adjusted_entries = 0

    def distribute(
        entry: TimeEntry, spans: list[tuple[datetime, datetime, bool]], minutes: float, kind: str
    ) -> None:
        total_seconds = sum((b - a).total_seconds() for a, b, _ in spans)
        if not total_seconds:
            return
        for span_start, span_end, running in spans:
            left, right = max(span_start, start), min(span_end, stop)
            while left < right:
                local = left.astimezone(zone)
                midnight = datetime.combine(
                    local.date() + timedelta(days=1), time.min, zone
                ).astimezone(UTC)
                piece_end = min(right, midnight)
                key = local.date().isoformat()
                elapsed = (piece_end - left).total_seconds()
                if key in days:
                    field = "recordedMinutes" if entry.state == "COMPLETED" else "pendingMinutes"
                    days[key][field] += minutes * elapsed / total_seconds
                    slices[key].append((left, piece_end))
                    end_local = piece_end.astimezone(zone)
                    segments.append(
                        {
                            **card_info(entry.demand_id),
                            "entryId": str(entry.id),
                            "kind": kind,
                            "date": key,
                            "startedAt": left,
                            "endedAt": piece_end,
                            "running": running,
                            "startMinute": local.hour * 60 + local.minute + local.second / 60,
                            "endMinute": 1440
                            if end_local.date() != local.date()
                            else end_local.hour * 60 + end_local.minute + end_local.second / 60,
                            "minutes": round(elapsed / 60, 2),
                        }
                    )
                left = piece_end

    own_entries = [
        entry
        for entry in entries
        if entry.user_profile_id == profile_id
        and not entry.deleted_at
        and entry.demand_id in card_map
    ]
    for entry in own_entries:
        history = entry_events[str(entry.id)]
        edited = any(e.kind == "TIME_ENTRY_UPDATED" for e in history)
        # Manual adjustments carry their explicitly supplied interval, not a claimed timer trace.
        if entry.source == "MANUAL" or edited:
            if entry.ended_at and entry.ended_at > start and entry.started_at < stop:
                adjusted_entries += int(edited)
                distribute(
                    entry,
                    [(entry.started_at, entry.ended_at, False)],
                    float(entry.duration_minutes or 0),
                    "adjusted" if edited else "manual",
                )
        else:
            spans = (
                timer_spans(entry, history, now)
                if any(e.kind == "TIMER_STARTED" for e in history)
                else []
            )
            if spans:
                stored = float(entry.duration_minutes or 0)
                if entry.state == "RUNNING":
                    stored += sum(
                        (b - a).total_seconds() / 60 for a, b, running in spans if running
                    )
                observed_minutes = sum((b - a).total_seconds() / 60 for a, b, _ in spans)
                allowance = max(2, 1 + sum(e.kind == "TIMER_PAUSED" for e in history))
                if abs(observed_minutes - stored) > allowance:
                    spans = []
            if spans:
                distribute(entry, spans, stored, "timer")
            elif entry.state == "RUNNING" and entry.started_at < stop:
                # The current start is recorded even if older pause events are unavailable.
                distribute(
                    entry,
                    [(entry.started_at, now, True)],
                    max(0, (now - entry.started_at).total_seconds() / 60),
                    "timer",
                )
                unlocated_pending_minutes += float(entry.duration_minutes or 0)
            elif entry.ended_at and inside(entry.ended_at):
                # Historical durations remain valid without inventing their hourly distribution.
                key = entry.ended_at.astimezone(zone).date().isoformat()
                field = "recordedMinutes" if entry.state == "COMPLETED" else "pendingMinutes"
                minutes = float(entry.duration_minutes or 0)
                days[key][field] += minutes
                unlocated_minutes += minutes
                uncertain_entries += 1
        for event in history:
            if event.kind in {"TIMER_STARTED", "TIMER_RESUMED"} and inside(timer_event_at(event)):
                key = timer_event_at(event).astimezone(zone).date().isoformat()
                days[key]["timerStarts" if event.kind == "TIMER_STARTED" else "timerResumes"] += 1
    selected = [
        v
        for v in visits
        if v.assignee_id == profile_id
        and v.left_at
        and inside(v.left_at)
        and actions.get(v.id) in {"ADVANCE", "COMPLETE"}
    ]
    selected.sort(key=lambda v: v.left_at or start)
    deliveries: dict[uuid.UUID, dict[str, Any]] = {}
    cadence = []
    for visit in selected:
        assert visit.left_at
        key = visit.left_at.astimezone(zone).date().isoformat()
        days[key]["stageAdvances"] += 1
        days[key]["deliveredCards"].add(visit.demand_id)
        cadence.append(
            {
                **card_info(visit.demand_id),
                "at": visit.left_at,
                "date": key,
                "kind": "advance",
                "stageName": (visit.acceptance_snapshot or {}).get("stageName") or "Etapa entregue",
            }
        )
        item = deliveries.setdefault(
            visit.demand_id,
            {
                **card_info(visit.demand_id),
                "advancedAt": visit.left_at,
                "lastAdvancedAt": visit.left_at,
                "stageAdvances": 0,
                "completedAt": None,
                "outcome": "awaiting",
            },
        )
        item["lastAdvancedAt"] = visit.left_at
        item["stageAdvances"] += 1
        if finals.get(visit.demand_id) and finals[visit.demand_id] >= visit.left_at:
            item["completedAt"] = finals[visit.demand_id]
            item["outcome"] = "completed"
    returns = []
    for visit in visits:
        if (
            visit.assignee_id == profile_id
            and not visit.inferred
            and visit.action == "RETURN"
            and inside(visit.entered_at)
        ):
            key = visit.entered_at.astimezone(zone).date().isoformat()
            days[key]["returns"] += 1
            returns.append(
                {
                    **card_info(visit.demand_id),
                    "at": visit.entered_at,
                    "reason": visit.reason,
                    "stageId": str(visit.workflow_stage_id),
                }
            )
            cadence.append(
                {
                    **card_info(visit.demand_id),
                    "at": visit.entered_at,
                    "date": key,
                    "kind": "return",
                    "stageName": "Retorno recebido",
                }
            )
    # First-pass outcomes per card + stage submitted in the selected cohort.
    approval_groups = {}
    for visit in selected:
        group_key = (visit.demand_id, visit.workflow_stage_id, visit.workflow_version_id)
        if group_key in approval_groups:
            continue
        version = versions.get(visit.workflow_version_id)
        stage_list = sorted(
            (version.definition if version else {}).get("stages", []),
            key=lambda s: s.get("position", 0),
        )
        positions = version_positions(version)
        own_position = positions.get(str(visit.workflow_stage_id), -1)
        approval_ids = {
            str(s["id"])
            for s in stage_list
            if s.get("id")
            and positions.get(str(s["id"]), -1) > own_position
            and any(
                word in str(s.get("name", "")).casefold() for word in ("aprova", "revis", "valida")
            )
        }
        source_stage: dict[str, Any] = next(
            (s for s in stage_list if str(s.get("id")) == str(visit.workflow_stage_id)), {}
        )
        if not approval_ids or any(
            word in str(source_stage.get("name", "")).casefold()
            for word in ("aprova", "revis", "valida")
        ):
            continue
        later = [
            v
            for v in by_card[visit.demand_id]
            if v.visit_number > visit.visit_number
            and v.entered_at <= now
            and v.workflow_version_id == visit.workflow_version_id
            and not v.inferred
        ]
        returned = any(
            v.action == "RETURN"
            and v.workflow_stage_id == visit.workflow_stage_id
            and v.assignee_id == profile_id
            for v in later
        )
        approved = any(
            str(v.workflow_stage_id) in approval_ids
            and v.assignee_id
            and v.assignee_id != profile_id
            and v.left_at
            and v.left_at <= now
            and actions.get(v.id) in {"ADVANCE", "COMPLETE"}
            for v in later
        )
        state = "rework" if returned else "approved" if approved else "pending"
        approval_groups[group_key] = {
            **card_info(visit.demand_id),
            "stageName": source_stage.get("name", "Etapa"),
            "outcome": state,
        }
    approval_counts = {
        state: sum(item["outcome"] == state for item in approval_groups.values())
        for state in ["approved", "rework", "pending"]
    }
    decisions = approval_counts["approved"] + approval_counts["rework"]
    alerts: list[dict[str, Any]] = []
    active = [
        card
        for card in cards
        if card.current_assignee_id == profile_id
        and card.status != "COMPLETED"
        and not card.archived_at
        and not card.deleted_at
    ]
    overdue = [card for card in active if card.deadline_at and card.deadline_at < now]
    if overdue:
        alerts.append(
            {
                "id": "overdue",
                "tone": "warning",
                "title": f"{len(overdue)} demanda(s) com prazo vencido",
                "description": "Revise os próximos passos e alinhe as entregas pendentes.",
                "demandId": str(overdue[0].id),
            }
        )
    returns.sort(key=lambda item: item["at"], reverse=True)
    for item in returns[:5]:
        current = card_map[uuid.UUID(item["id"])]
        needs_attention = (
            current.current_assignee_id == profile_id
            and current.status != "COMPLETED"
            and not current.archived_at
            and not current.deleted_at
            and str(current.current_stage_id) == item["stageId"]
        )
        when = item["at"].astimezone(zone).strftime("%d/%m %H:%M")
        alerts.append(
            {
                "id": "return-" + item["id"] + item["at"].isoformat(),
                "tone": "warning" if needs_attention else "info",
                "title": "Uma entrega voltou para você"
                if needs_attention
                else "Retorno registrado no período",
                "description": f"{item['title']} · {when}. {item['reason'] or 'Confira o contexto no histórico da demanda.'}",
                "demandId": item["id"] if item["canOpen"] else None,
            }
        )
    gaps: list[dict[str, Any]] = []
    for key, day in days.items():
        merged = union_intervals(slices[key])
        day["coverageMinutes"] = round(sum((b - a).total_seconds() / 60 for a, b in merged), 1)
        local_day = date.fromisoformat(key)
        window_start = datetime.combine(local_day, day_start, zone).astimezone(UTC)
        window_end = min(datetime.combine(local_day, day_end, zone).astimezone(UTC), stop)
        observed = union_intervals(
            [
                (max(a, window_start), min(b, window_end))
                for a, b in merged
                if b > window_start and a < window_end
            ]
        )
        pairs = [(observed[i - 1][1], observed[i][0]) for i in range(1, len(observed))]
        if (
            local_day == now.astimezone(zone).date()
            and observed
            and now <= datetime.combine(local_day, day_end, zone).astimezone(UTC)
        ):
            pairs.append((observed[-1][1], window_end))
        for a, b in pairs:
            minutes = (b - a).total_seconds() / 60
            if minutes >= gap_minutes:
                gaps.append({"date": key, "startedAt": a, "endedAt": b, "minutes": round(minutes)})
        day["recordedMinutes"] = round(day["recordedMinutes"], 1)
        day["pendingMinutes"] = round(day["pendingMinutes"], 1)
        day["deliveredCards"] = len(day["deliveredCards"])
    if gaps:
        longest = max(gaps, key=lambda gap: gap["minutes"])
        alerts.append(
            {
                "id": "recording-gap",
                "tone": "info",
                "title": f"Intervalo de {longest['minutes']} min sem apontamento",
                "description": f"{longest['startedAt'].astimezone(zone).strftime('%d/%m %H:%M')}–{longest['endedAt'].astimezone(zone).strftime('%H:%M')}. Se estava em atividade, confira se falta registrar tempo. Pausas e horários sem registro não comprovam ausência de trabalho.",
                "demandId": None,
            }
        )
    # Personal references use closed cards of the same category/workflow and stage participation.
    totals: dict[uuid.UUID, float] = defaultdict(float)
    for entry in own_entries:
        if entry.state == "COMPLETED" and entry.ended_at and entry.ended_at <= now:
            totals[entry.demand_id] += float(entry.duration_minutes or 0)
    signatures: dict[uuid.UUID, frozenset[uuid.UUID]] = {}
    for card in cards:
        signatures[card.id] = frozenset(
            v.workflow_stage_id
            for v in by_card[card.id]
            if v.assignee_id == profile_id and actions.get(v.id) in {"ADVANCE", "COMPLETE"}
        )
    comparisons = []
    for identifier, item in deliveries.items():
        if item["outcome"] != "completed" or not totals[identifier]:
            continue
        card = card_map[identifier]
        finished = finals[identifier]
        sample = [
            totals[c.id]
            for c in cards
            if c.id != identifier
            and c.category_id is not None
            and c.category_id == card.category_id
            and c.workflow_id == card.workflow_id
            and signatures[c.id] == signatures[identifier]
            and c.id in finals
            and finished - timedelta(days=90) <= finals[c.id] < finished
            and totals[c.id] > 0
        ]
        if len(sample) < MIN_BASELINE_CARDS:
            continue
        typical = float(median(sample))
        ratio = totals[identifier] / typical
        state = "above" if ratio >= 1.5 else "below" if ratio <= 2 / 3 else "typical"
        comparisons.append(
            {
                **card_info(identifier),
                "minutes": round(totals[identifier], 1),
                "referenceMinutes": round(typical, 1),
                "sampleCards": len(sample),
                "outcome": state,
            }
        )
        if state != "typical":
            alerts.append(
                {
                    "id": "pace-" + str(identifier),
                    "tone": "info" if state == "above" else "positive",
                    "title": "Tempo acima da referência pessoal"
                    if state == "above"
                    else "Tempo abaixo da referência pessoal",
                    "description": f"{card.title} · {round(totals[identifier])} min; referência de {round(typical)} min em {len(sample)} cards comparáveis. Confira o contexto antes de avaliar a diferença.",
                    "demandId": str(identifier) if not card.deleted_at else None,
                }
            )
    if not comparisons and deliveries:
        alerts.append(
            {
                "id": "baseline-building",
                "tone": "info",
                "title": "Sua referência pessoal está em formação",
                "description": f"Comparações de tempo só aparecem com pelo menos {MIN_BASELINE_CARDS} outros cards concluídos de contexto equivalente. Não há avaliação presumida quando falta histórico.",
                "demandId": None,
            }
        )
    if unlocated_minutes:
        alerts.append(
            {
                "id": "trace-quality",
                "tone": "info",
                "title": "Há tempo sem distribuição por horário",
                "description": f"{round(unlocated_minutes)} min foram preservados no total, sem inventar uma linha de timer para registros sem histórico completo.",
                "demandId": None,
            }
        )
    if not sum(day["recordedMinutes"] + day["pendingMinutes"] for day in days.values()):
        alerts.append(
            {
                "id": "no-time",
                "tone": "info",
                "title": "Ainda não há tempo registrado neste período",
                "description": "Confira os timers e os apontamentos manuais. Falta de registro não comprova ausência de trabalho.",
                "demandId": None,
            }
        )
    completed_count = sum(item["outcome"] == "completed" for item in deliveries.values())
    if completed_count:
        alerts.append(
            {
                "id": "finals",
                "tone": "positive",
                "title": f"{completed_count} entrega(s) chegaram ao fim do fluxo",
                "description": "São cards que você avançou no período e que já tiveram conclusão final comprovada.",
                "demandId": None,
            }
        )
    return {
        "summary": {
            "recordedMinutes": round(sum(d["recordedMinutes"] for d in days.values()), 1),
            "pendingMinutes": round(sum(d["pendingMinutes"] for d in days.values()), 1),
            "coverageMinutes": round(sum(d["coverageMinutes"] for d in days.values()), 1),
            "stageAdvances": len(selected),
            "deliveredCards": len(deliveries),
            "completedAfterDelivery": completed_count,
            "awaitingFinal": len(deliveries) - completed_count,
            "returns": len(returns),
            "timerStarts": sum(d["timerStarts"] for d in days.values()),
            "timerResumes": sum(d["timerResumes"] for d in days.values()),
        },
        "days": list(days.values()),
        "segments": sorted(segments, key=lambda s: (s["startedAt"], s["id"])),
        "cadence": sorted(cadence, key=lambda item: item["at"]),
        "deliveries": list(deliveries.values()),
        "returns": returns,
        "approval": {
            "counts": approval_counts,
            "decided": decisions,
            "approvalRate": round(approval_counts["approved"] / decisions * 100)
            if decisions
            else None,
            "reworkRate": round(approval_counts["rework"] / decisions * 100) if decisions else None,
            "items": list(approval_groups.values()),
        },
        "alerts": alerts,
        "gaps": gaps,
        "comparisons": comparisons,
        "quality": {
            "unlocatedMinutes": round(unlocated_minutes, 1),
            "unlocatedPendingMinutes": round(unlocated_pending_minutes, 1),
            "entriesWithoutTrace": uncertain_entries,
            "adjustedEntries": adjusted_entries,
            "baselineMinimum": MIN_BASELINE_CARDS,
        },
        "generatedAt": now,
    }
