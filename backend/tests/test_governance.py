import json

import pytest

from app.api.errors import ApiError
from app.governance import (
    best_named_match,
    best_profile_match,
    canonical_hash,
    card_snapshot,
    priority_for_card,
    status_for_list,
    validate_trello_document,
)


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
