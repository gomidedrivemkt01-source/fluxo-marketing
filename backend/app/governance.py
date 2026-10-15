"""Funcoes puras usadas pela importacao Trello e pela retencao."""

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from app.api.errors import ApiError

MAX_TRELLO_BYTES = 25 * 1024 * 1024


def normalized(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text.upper()).split())


def parse_source_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)
    except ValueError:
        return None


def trello_object_created_at(value: str | None) -> datetime | None:
    if not value or not re.fullmatch(r"[0-9a-fA-F]{24}", value):
        return None
    try:
        return datetime.fromtimestamp(int(value[:8], 16), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_trello_document(raw: bytes) -> dict[str, Any]:
    if not raw:
        raise ApiError(422, "trello_empty_file", "O arquivo JSON está vazio.")
    if len(raw) > MAX_TRELLO_BYTES:
        raise ApiError(413, "trello_file_too_large", "O JSON pode ter no máximo 25 MB.")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError(422, "trello_invalid_json", "O arquivo não contém um JSON válido.") from exc
    if not isinstance(document, dict):
        raise ApiError(422, "trello_invalid_root", "O export deve representar um quadro do Trello.")
    required = {"id": str, "name": str, "lists": list, "cards": list}
    for field, expected in required.items():
        if not isinstance(document.get(field), expected):
            raise ApiError(422, "trello_invalid_structure", f"Campo obrigatório inválido: {field}.")
    list_ids = {item.get("id") for item in document["lists"] if isinstance(item, dict)}
    card_ids: set[str] = set()
    for index, card in enumerate(document["cards"]):
        if not isinstance(card, dict) or not isinstance(card.get("id"), str) or not card.get("id"):
            raise ApiError(422, "trello_invalid_card", f"Cartão inválido na posição {index + 1}.")
        if card["id"] in card_ids:
            raise ApiError(
                422,
                "trello_duplicate_card",
                f"O cartão {card['id']} aparece duas vezes no arquivo.",
            )
        card_ids.add(card["id"])
        if not isinstance(card.get("name"), str):
            raise ApiError(422, "trello_invalid_card", f"Cartão sem título na posição {index + 1}.")
        if card.get("idList") not in list_ids:
            raise ApiError(
                422,
                "trello_unknown_list",
                f"O cartão {card['id']} aponta para uma lista inexistente.",
            )
    return document


def status_for_list(name: str) -> str:
    value = normalized(name)
    if any(token in value for token in ("CONCLUID", "FINALIZ", "ENTREG")):
        return "COMPLETED"
    if "PAUS" in value:
        return "BLOCKED"
    if "AGEND" in value:
        return "SCHEDULED"
    if "APROVA" in value:
        return "WAITING_APPROVAL"
    if any(token in value for token in ("PRODUC", "ANDAMENTO", "EXECUCAO")):
        return "IN_PROGRESS"
    return "WAITING_EXECUTION"


def priority_for_card(card: dict[str, Any], list_name: str, label_names: list[str]) -> str:
    combined = normalized(" ".join([list_name, *label_names]))
    if "URGENT" in combined:
        return "URGENT"
    if any(token in combined for token in ("PRIORIDADE", "ALTA", "HIGH")):
        return "HIGH"
    return "NORMAL"


def card_snapshot(
    card: dict[str, Any],
    *,
    lists_by_id: dict[str, dict[str, Any]],
    labels_by_id: dict[str, dict[str, Any]],
    checklists_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    checklist_ids = [str(value) for value in card.get("idChecklists", []) if value]
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "desc": card.get("desc"),
        "list": lists_by_id.get(str(card.get("idList")), {}),
        "members": sorted(str(value) for value in card.get("idMembers", []) if value),
        "labels": sorted(
            (
                {
                    "id": str(label.get("id")),
                    "name": label.get("name"),
                    "color": label.get("color"),
                }
                for label_id in card.get("idLabels", [])
                if (label := labels_by_id.get(str(label_id)))
            ),
            key=lambda item: item["id"],
        ),
        "due": card.get("due"),
        "dueComplete": bool(card.get("dueComplete")),
        "closed": bool(card.get("closed")),
        "dateLastActivity": card.get("dateLastActivity"),
        "shortLink": card.get("shortLink"),
        "url": card.get("url"),
        "attachments": [
            {"id": item.get("id"), "name": item.get("name"), "url": item.get("url")}
            for item in card.get("attachments", [])
            if isinstance(item, dict)
        ],
        "checklists": [
            checklists_by_id[value] for value in checklist_ids if value in checklists_by_id
        ],
    }


def best_named_match(source_name: str, candidates: list[tuple[str, str]]) -> str | None:
    source = normalized(source_name)
    if not source:
        return None
    exact = [identifier for identifier, name in candidates if normalized(name) == source]
    if len(exact) == 1:
        return exact[0]
    partial = [
        identifier
        for identifier, name in candidates
        if source in normalized(name) or normalized(name) in source
    ]
    return partial[0] if len(partial) == 1 else None


def best_profile_match(source_name: str, candidates: list[tuple[str, str, str]]) -> str | None:
    """Match a Trello member to an active profile without guessing ambiguous names."""

    source = normalized(source_name)
    if not source:
        return None

    aliases: dict[str, set[str]] = {}
    for identifier, full_name, email in candidates:
        values = {normalized(full_name), normalized(email)}
        if "@" in email:
            values.add(normalized(email.split("@", 1)[0]))
        aliases[identifier] = {value for value in values if value}

    exact = [identifier for identifier, values in aliases.items() if source in values]
    if len(exact) == 1:
        return exact[0]

    ignored_tokens = {"DA", "DAS", "DE", "DO", "DOS", "E"}
    source_tokens = {token for token in source.split() if token not in ignored_tokens}
    token_matches = []
    if len(source_tokens) >= 2:
        for identifier, full_name, _email in candidates:
            candidate_tokens = {
                token for token in normalized(full_name).split() if token not in ignored_tokens
            }
            if source_tokens <= candidate_tokens or candidate_tokens <= source_tokens:
                token_matches.append(identifier)
    if len(token_matches) == 1:
        return token_matches[0]

    compact_source = source.replace(" ", "")
    if len(compact_source) < 8:
        return None
    scored = []
    for identifier, values in aliases.items():
        score = max(
            (
                SequenceMatcher(None, compact_source, value.replace(" ", "")).ratio()
                for value in values
            ),
            default=0.0,
        )
        if score >= 0.92:
            scored.append((score, identifier))
    scored.sort(reverse=True)
    if not scored:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.03:
        return None
    return scored[0][1]
