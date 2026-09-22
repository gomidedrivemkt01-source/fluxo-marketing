import pytest
from pydantic import ValidationError

from app.api.daily_imports import DailyDocument, MappingRequest


def valid_document() -> dict[str, object]:
    return {
        "schemaVersion": "2.0",
        "importType": "DAILY_REVIEW",
        "batchId": "daily-2026-09-22-01",
        "source": {"type": "DAILY_REPORT", "date": "2026-09-22", "label": "Daily"},
        "items": [
            {
                "itemId": "ITEM-001",
                "reference": {"titleHint": "Reels Reforma Tributária"},
                "summary": "Edição em andamento.",
                "sourceExcerpt": "A edição deve ficar pronta hoje.",
                "proposals": [
                    {
                        "proposalId": "P01",
                        "type": "SET_STATUS",
                        "payload": {"value": "IN_PROGRESS"},
                    }
                ],
            }
        ],
    }


def test_daily_document_accepts_v2_and_rejects_unknown_fields() -> None:
    document = DailyDocument.model_validate(valid_document())
    assert document.items[0].reference.title_hint == "Reels Reforma Tributária"
    invalid = valid_document()
    invalid["automaticApply"] = True
    with pytest.raises(ValidationError):
        DailyDocument.model_validate(invalid)


def test_daily_document_rejects_duplicate_item_ids() -> None:
    invalid = valid_document()
    items = invalid["items"]
    assert isinstance(items, list)
    items.append(dict(items[0]))
    with pytest.raises(ValidationError):
        DailyDocument.model_validate(invalid)


def test_mapping_requires_explicit_destination_or_title() -> None:
    with pytest.raises(ValidationError):
        MappingRequest.model_validate({"action": "map"})
    with pytest.raises(ValidationError):
        MappingRequest.model_validate({"action": "create"})
    assert MappingRequest.model_validate({"action": "ignore"}).action == "ignore"
