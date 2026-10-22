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


TRELLO_COMPANY_NAMES = {
    "ANDERSON_NUNES": "Anderson Nunes",
    "ECLUSA": "Eclusa",
    "ELOFISCAL": "EloFiscal",
    "EXPERT_CONSULTORIA": "Expert Consultoria",
    "GOMIDE_CONTABILIDADE": "Gomide Contabilidade",
    "GOMIDE_OLIVEIRA_ADVOGADOS": "Gomide e Oliveira Advogados",
    "IMPOSTO_NO_BOLSO": "Imposto no Bolso",
    "RAFAEL_OLIVEIRA": "Rafael Oliveira",
    "RETRIBUTARIA": "Retributária",
}


TRELLO_CATEGORY_ALIASES = {
    "AUTOMACAO": "AUTOMATION",
    "BLOG": "BLOG",
    "BLOGS": "BLOG",
    "CAMPANHA": "CAMPAIGN",
    "CAMPANHAS": "CAMPAIGN",
    "CARROSSEL": "CAROUSEL",
    "CARROSSSEL": "CAROUSEL",
    "ENDOMARKETING": "INTERNAL_MARKETING",
    "ENDORMAKETING": "INTERNAL_MARKETING",
    "ESTATICO": "STATIC",
    "EVENTO": "EVENT",
    "LANDING PAGE": "LANDING_PAGE",
    "LP": "LANDING_PAGE",
    "MATERIAL GRAFICO": "GRAPHIC_MATERIAL",
    "OOH": "GRAPHIC_MATERIAL",
    "REELS": "VIDEO_REELS",
    "STORIES": "STORY",
    "STORY": "STORY",
    "VIDEO": "VIDEO_REELS",
    "VIDEO REELS": "VIDEO_REELS",
    "VIDEO YOUTUBE": "VIDEO_YOUTUBE",
    "YOUTUBE": "VIDEO_YOUTUBE",
}


def normalized(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text.upper()).split())


def trello_company_name(title: str | None) -> str | None:
    """Resolve marcas do quadro sem confundir abreviações com palavras do título."""

    raw_title = title or ""
    value = normalized(raw_title)
    prefix = normalized(raw_title.split("|", 1)[0]) if "|" in raw_title else ""

    # Nomes compostos precisam ser avaliados antes de "Gomide" isolado.
    if any(token in value for token in ("GOMIDE E OLIVEIRA", "GOMIDE OLIVEIRA", "GOMIDE ADVOCA")):
        return TRELLO_COMPANY_NAMES["GOMIDE_OLIVEIRA_ADVOGADOS"]

    structured_aliases = (
        (("G OLIVEIRA", "GOA"), "GOMIDE_OLIVEIRA_ADVOGADOS"),
        (("GOM",), "GOMIDE_CONTABILIDADE"),
        (("EXP",), "EXPERT_CONSULTORIA"),
        (("IMP",), "IMPOSTO_NO_BOLSO"),
        (("ELO",), "ELOFISCAL"),
        (("ECL",), "ECLUSA"),
        (("RAF", "RAFAEL"), "RAFAEL_OLIVEIRA"),
        (("AND",), "ANDERSON_NUNES"),
        (("RET", "RETRIB"), "RETRIBUTARIA"),
    )
    if prefix and prefix not in {"INTERNO", "TODAS AS EMPRESAS", "VALIDAR"}:
        for aliases, company_key in structured_aliases:
            if any(prefix == alias or prefix.startswith(f"{alias} ") for alias in aliases):
                return TRELLO_COMPANY_NAMES[company_key]

    explicit_names = (
        (("IMPOSTO NO BOLSO",), "IMPOSTO_NO_BOLSO"),
        (("GOMIDE CONTABILIDADE",), "GOMIDE_CONTABILIDADE"),
        (("EXPERT CONSULTORIA", "EXPERT"), "EXPERT_CONSULTORIA"),
        (("ELOFISCAL", "ELO FISCAL"), "ELOFISCAL"),
        (("ECLUSA",), "ECLUSA"),
        (("RAFAEL OLIVEIRA",), "RAFAEL_OLIVEIRA"),
        (("ANDERSON NUNES",), "ANDERSON_NUNES"),
        (("RETRIBUTARIA",), "RETRIBUTARIA"),
    )
    for aliases, company_key in explicit_names:
        if any(alias in value for alias in aliases):
            return TRELLO_COMPANY_NAMES[company_key]

    # O quadro histórico usa estes nomes simples como marca no início ou fim do título.
    if re.search(r"(?:^| )GOMIDE(?:$| )", value):
        return TRELLO_COMPANY_NAMES["GOMIDE_CONTABILIDADE"]
    if re.search(r"(?:^| )ANDERSON(?:$| )", value):
        return TRELLO_COMPANY_NAMES["ANDERSON_NUNES"]
    return None


def trello_category_code(title: str | None, label_names: list[str] | None = None) -> str | None:
    """Classifica apenas formatos explícitos; títulos ambíguos permanecem sem categoria."""

    for label in label_names or []:
        if code := TRELLO_CATEGORY_ALIASES.get(normalized(label)):
            return code

    raw_title = title or ""
    segments = raw_title.split("|")
    if len(segments) > 1:
        structured_type = normalized(segments[1])
        if "YOUTUBE" in structured_type:
            return "VIDEO_YOUTUBE"
        for alias, code in TRELLO_CATEGORY_ALIASES.items():
            if structured_type == alias or structured_type.startswith(f"{alias} "):
                return code
        if structured_type == "PLANEJAMENTO":
            return "CAMPAIGN"

    value = normalized(raw_title)
    if "YOUTUBE" in value and re.search(r"(?:^| )VIDEO(?:$| )", value):
        return "VIDEO_YOUTUBE"
    patterns = (
        (r"^(?:EDICAO DE? |EDITAR O? )?VIDEOS?\b", "VIDEO_REELS"),
        (r"^ALTERACOES CAPA DO REELS\b", "VIDEO_REELS"),
        (r"^(?:BLOG|BLOGS)\b", "BLOG"),
        (r"^CARROSS?SEL\b", "CAROUSEL"),
        (r"^(?:ESTATICO|POST ESTATICO)\b", "STATIC"),
        (r"^(?:STORY|STORIES)\b", "STORY"),
        (r"^(?:ENDOMARKETING|ENDORMAKETING)\b", "INTERNAL_MARKETING"),
        (r"^(?:CAMPANHA|RELATORIO DE CAMPANHAS)\b", "CAMPAIGN"),
        (r"^(?:LP|LANDING PAGE)\b", "LANDING_PAGE"),
        (r"^(?:OOH|MATERIAL GRAFICO)\b", "GRAPHIC_MATERIAL"),
        (r"^EVENTO\b", "EVENT"),
        (r"^SYSTEM\b", "AUTOMATION"),
    )
    for pattern, code in patterns:
        if re.search(pattern, value):
            return code
    return None


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


TITLE_DATE_PATTERN = re.compile(
    r"(?<!\d)(?P<day>0?[1-9]|[12]\d|3[01])\s*[/.-]\s*"
    r"(?P<month>0?[1-9]|1[0-2])"
    r"(?:\s*(?:[/.-]|-\s*)\s*(?P<year>(?:20)?\d{2}))?(?!\d)"
)


def trello_deadline_from_title(
    title: str | None, reference: datetime | None = None
) -> datetime | None:
    """Extrai a primeira data DD/MM do título usando o ano do próprio card.

    O quadro histórico usa datas editoriais sem ano. Nesses casos, o ano da
    última atividade é a referência mais segura. O horário de 20h UTC equivale
    a 17h em Brasília e evita que a data mude na interface.
    """

    match = TITLE_DATE_PATTERN.search(title or "")
    if not match:
        return None
    year_text = match.group("year")
    year = int(year_text) if year_text else (reference or datetime.now(UTC)).year
    if year < 100:
        year += 2000
    try:
        return datetime(
            year,
            int(match.group("month")),
            int(match.group("day")),
            20,
            tzinfo=UTC,
        )
    except ValueError:
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
            trello_attachment_snapshot(item)
            for item in card.get("attachments", [])
            if isinstance(item, dict)
        ],
        "checklists": [
            checklists_by_id[value] for value in checklist_ids if value in checklists_by_id
        ],
    }


def trello_attachment_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    previews = [value for value in item.get("previews", []) if isinstance(value, dict)]
    preview = max(
        previews,
        key=lambda value: int(value.get("width") or 0) * int(value.get("height") or 0),
        default=None,
    )
    return {
        "id": item.get("id"),
        "name": item.get("name") or item.get("fileName"),
        "fileName": item.get("fileName"),
        "url": item.get("url"),
        "previewUrl": preview.get("url") if preview else None,
        "mimeType": item.get("mimeType"),
        "bytes": item.get("bytes"),
        "date": item.get("date"),
        "idMember": item.get("idMember"),
        "isUpload": bool(item.get("isUpload")),
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

    name_match = best_named_match(
        source_name, [(identifier, full_name) for identifier, full_name, _email in candidates]
    )
    if name_match:
        return name_match

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
