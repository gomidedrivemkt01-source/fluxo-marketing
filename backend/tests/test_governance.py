import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.governance import (
    imported_demand_sources,
    trello_action_description,
    trello_attachment_size,
    trello_reset_preview,
    valid_external_url,
)
from app.governance import (
    best_named_match,
    best_profile_match,
    canonical_hash,
    card_snapshot,
    priority_for_card,
    status_for_list,
    trello_category_code,
    trello_company_name,
    trello_deadline_from_title,
    validate_trello_document,
)
from app.models import Demand, DemandUpdate


def trello_document() -> dict:
    return {
        "id": "685eda31d6f078c8475dddc7",
        "name": "MARKETING",
        "lists": [{"id": "list-1", "name": "EM PRODUÇÃO", "pos": 1}],
        "cards": [
            {
                "id": "66f000000000000000000001",
                "name": "Vídeo institucional",
                "desc": "Roteiro e gravação",
                "idList": "list-1",
                "idMembers": ["member-1"],
                "idLabels": ["label-1"],
                "idChecklists": ["check-1"],
                "attachments": [],
            }
        ],
        "labels": [{"id": "label-1", "name": "Urgente", "color": "red"}],
        "checklists": [
            {
                "id": "check-1",
                "name": "Produção",
                "checkItems": [{"id": "item-1", "name": "Revisar roteiro", "state": "complete"}],
            }
        ],
        "members": [{"id": "member-1", "fullName": "João Guimarães"}],
    }


def test_validates_full_trello_export_and_builds_stable_snapshot() -> None:
    document = trello_document()
    validated = validate_trello_document(json.dumps(document).encode())
    snapshot = card_snapshot(
        validated["cards"][0],
        lists_by_id={"list-1": document["lists"][0]},
        labels_by_id={"label-1": document["labels"][0]},
        checklists_by_id={"check-1": document["checklists"][0]},
    )
    assert snapshot["list"]["name"] == "EM PRODUÇÃO"
    assert snapshot["checklists"][0]["checkItems"][0]["state"] == "complete"
    assert canonical_hash(snapshot) == canonical_hash(dict(reversed(list(snapshot.items()))))


def test_rejects_cards_that_reference_an_unknown_list() -> None:
    document = trello_document()
    document["cards"][0]["idList"] = "missing"
    with pytest.raises(ApiError) as error:
        validate_trello_document(json.dumps(document).encode())
    assert error.value.code == "trello_unknown_list"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("🎉 CONCLUÍDO", "COMPLETED"),
        ("PAUSADAS", "BLOCKED"),
        ("AGENDADO", "SCHEDULED"),
        ("APROVAÇÃO", "WAITING_APPROVAL"),
        ("EM PRODUÇÃO", "IN_PROGRESS"),
        ("BACKLOG", "WAITING_EXECUTION"),
    ],
)
def test_maps_trello_lists_to_operational_status(name: str, expected: str) -> None:
    assert status_for_list(name) == expected


def test_matches_accents_and_maps_priority() -> None:
    assert best_named_match("João Guimarães", [("one", "Joao Guimaraes")]) == "one"
    assert priority_for_card({}, "URGENTE (PRIORIDADE)", []) == "URGENT"


@pytest.mark.parametrize(
    ("title", "reference", "expected"),
    [
        (
            "🟡 G. OLIVEIRA | BLOG | 04/12 | Tema",
            datetime(2026, 10, 13, tzinfo=UTC),
            datetime(2026, 12, 4, 20, tzinfo=UTC),
        ),
        (
            "GOM | REELS | 21/10 - 2026 é ano de testar",
            datetime(2025, 10, 13, tzinfo=UTC),
            datetime(2026, 10, 21, 20, tzinfo=UTC),
        ),
        ("Card sem data", datetime(2026, 10, 13, tzinfo=UTC), None),
        ("Data inválida 31/02", datetime(2026, 10, 13, tzinfo=UTC), None),
    ],
)
def test_extracts_trello_deadline_from_title(
    title: str, reference: datetime, expected: datetime | None
) -> None:
    assert trello_deadline_from_title(title, reference) == expected


def test_matches_trello_members_by_name_tokens_and_email_username_typo() -> None:
    profiles = [
        ("natalia", "Natália De Araujo Vieira", "nataliavieira2622@gmail.com"),
        ("maria", "Maria Fernanda Tavares", "maria@example.com"),
    ]
    assert best_profile_match("Natália Vieira", profiles) == "natalia"
    assert best_profile_match("nataliavieia2622", profiles) == "natalia"


def test_matches_unique_short_profile_alias() -> None:
    profiles = [
        ("marketing", "Marketing Gomide Contabilidade", "gomidedrivemkt01@gmail.com"),
        ("maria", "Maria Fernanda Tavares", "maria@example.com"),
        ("sivas", "Sivas Junior", "sivas@gomidecontabilidade.com.br"),
    ]
    assert best_profile_match("Gomide", profiles) == "marketing"


def test_does_not_guess_ambiguous_profile_names() -> None:
    profiles = [
        ("first", "João Silva", "joao.silva@example.com"),
        ("second", "João Santos", "joao.santos@example.com"),
    ]
    assert best_profile_match("João", profiles) is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("🔴 GOM | BLOG | Reforma tributária", "Gomide Contabilidade"),
        ("🟡G. OLIVEIRA | REELS | Holding", "Gomide e Oliveira Advogados"),
        ("Vídeo holding - Gomide Oliveira", "Gomide e Oliveira Advogados"),
        ("CARROSSEL - IMPOSTO NO BOLSO", "Imposto no Bolso"),
        ("[ESTATICO] - ELOFISCAL", "EloFiscal"),
        ("⚪ TODAS AS EMPRESAS | BLOG | Informe", None),
    ],
)
def test_maps_explicit_trello_company_aliases(title: str, expected: str | None) -> None:
    assert trello_company_name(title) == expected


@pytest.mark.parametrize(
    ("title", "labels", "expected"),
    [
        ("🔴 GOM | CARROSSEL | Reforma", [], "CAROUSEL"),
        ("🔵 EXP | VÍDEO | Entrevista", [], "VIDEO_REELS"),
        ("vídeo Natali - Youtube", [], "VIDEO_YOUTUBE"),
        ("BLOGS DA SEMANA - SEMANA 1", [], "BLOG"),
        ("LP PRODUTOS DA REFORMA", [], "LANDING_PAGE"),
        ("Pauta sem formato explícito", ["📰 BLOG"], "BLOG"),
        ("RELATÓRIO VENDAS", [], None),
    ],
)
def test_maps_only_explicit_trello_category_formats(
    title: str, labels: list[str], expected: str | None
) -> None:
    assert trello_category_code(title, labels) == expected


def test_detects_operational_edits_after_trello_import() -> None:
    demand_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    imported_at = datetime(2026, 10, 19, 12, tzinfo=UTC)
    demand = Demand(
        id=demand_id,
        organization_id=uuid.uuid4(),
        public_id="DMD-2026-000001",
        title="Card importado",
        source="trello_import",
        created_by=actor_id,
    )
    trello_update = DemandUpdate(
        demand_id=demand_id,
        created_by=actor_id,
        kind="trello_import",
        summary="Importada",
        payload={"trello": {"name": "🔴 GOM | BLOG | Card importado"}},
        created_at=imported_at,
    )
    manual_update = DemandUpdate(
        demand_id=demand_id,
        created_by=actor_id,
        kind="STAGE_CHANGED",
        summary="Etapa alterada",
        payload={},
        created_at=imported_at + timedelta(minutes=5),
    )
    db = MagicMock(spec=Session)
    db.scalars.return_value = iter([manual_update, trello_update])

    sources, protected = imported_demand_sources(db, [demand])

    assert sources[demand_id]["name"].endswith("Card importado")
    assert protected == {demand_id}


def test_trello_reset_preview_counts_only_operational_import_data() -> None:
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [
        0,  # linked existing demands
        980,  # demands
        336,  # active
        644,  # archived
        644,  # soft deleted by the previous batch revert
        0,  # time entries
        980,  # stage visits
        980,  # state intervals
        980,  # updates
        89,  # todo items
        0,  # files
        547,  # revisions
        0,  # daily links
        980,  # card links
        1,  # batches
    ]

    preview = trello_reset_preview(db, uuid.uuid4())

    assert preview["safeToReset"] is True
    assert preview["counts"]["demands"] == 980
    assert preview["counts"]["archivedDemands"] == 644
    assert preview["counts"]["revisions"] == 547
    assert "Workflows, etapas e modelos de checklist" in preview["preserved"]


def test_trello_reset_preview_blocks_physical_files_and_existing_demands() -> None:
    db = MagicMock(spec=Session)
    values = [0] * 15
    values[0] = 2  # linked existing demands
    values[10] = 3  # files
    db.scalar.side_effect = values

    preview = trello_reset_preview(db, uuid.uuid4())

    assert preview["safeToReset"] is False
    assert preview["counts"]["files"] == 3
    assert preview["counts"]["linkedExistingDemands"] == 2


def test_describes_trello_stage_change_but_skips_position_only_updates() -> None:
    moved = trello_action_description(
        {
            "type": "updateCard",
            "data": {
                "listBefore": {"name": "Copy"},
                "listAfter": {"name": "Aprovação"},
            },
        }
    )
    position_only = trello_action_description({"type": "updateCard", "data": {"old": {"pos": 123}}})

    assert moved == (
        "TRELLO_STAGE_CHANGED",
        "Movido no Trello: Copy → Aprovação.",
        None,
    )
    assert position_only is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://trello.com/c/example", "https://trello.com/c/example"),
        ("http://example.com/file.png", "http://example.com/file.png"),
        ("javascript:alert(1)", None),
        ("/relative/file.png", None),
        (None, None),
    ],
)
def test_accepts_only_http_external_attachment_urls(value: object, expected: str | None) -> None:
    assert valid_external_url(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2048, 2048),
        ("512", 512),
        (0, 1),
        (None, 1),
        ("unknown", 1),
    ],
)
def test_normalizes_trello_attachment_size_to_positive_bytes(value: object, expected: int) -> None:
    assert trello_attachment_size(value) == expected
