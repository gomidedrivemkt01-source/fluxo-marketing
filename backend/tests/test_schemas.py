import pytest
from pydantic import ValidationError

from app.api.users import PreferencesUpdate
from app.auth.schemas import RegisterRequest, VerifyRequest


def test_register_requires_long_password() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            name="Pessoa Teste",
            email="pessoa@example.com",
            password="curta",
            privacyNoticeVersion="draft-1",
        )


def test_verification_code_accepts_six_to_eight_digits() -> None:
    six_digits = VerifyRequest(email="pessoa@example.com", code="123456", purpose="signup")
    eight_digits = VerifyRequest(email="pessoa@example.com", code="12345678", purpose="signup")
    assert six_digits.code == "123456"
    assert eight_digits.code == "12345678"
    with pytest.raises(ValidationError):
        VerifyRequest(email="pessoa@example.com", code="12345", purpose="signup")
    with pytest.raises(ValidationError):
        VerifyRequest(email="pessoa@example.com", code="12345x", purpose="signup")


def test_preferences_accept_focus_views() -> None:
    preferences = PreferencesUpdate(
        demandView="list",
        showEmptyStages=False,
        stageOrder=[],
        focusView="today",
        savedViews=[
            {
                "id": "minha-visao",
                "name": "  Urgentes hoje  ",
                "query": "campanha",
                "companyId": "ALL",
                "status": "ALL",
                "priority": "URGENT",
                "focusView": "today",
            }
        ],
        personalColumns=[
            {"id": "fila", "name": "  Minha fila  ", "color": "#0F766E"},
            {"id": "fazendo", "name": "Fazendo", "color": "#2563EB"},
        ],
        personalPlacements={"demand-id": "fazendo"},
    )
    assert preferences.focus_view == "today"
    assert preferences.saved_views[0].name == "Urgentes hoje"
    assert preferences.personal_columns[0].name == "Minha fila"
    assert preferences.personal_placements["demand-id"] == "fazendo"


def test_preferences_require_at_least_one_personal_column() -> None:
    with pytest.raises(ValidationError):
        PreferencesUpdate(
            demandView="kanban",
            showEmptyStages=True,
            stageOrder=[],
            focusView="all",
            personalColumns=[],
        )


def test_preferences_reject_unknown_focus_view() -> None:
    with pytest.raises(ValidationError):
        PreferencesUpdate(
            demandView="list",
            showEmptyStages=False,
            stageOrder=[],
            focusView="tomorrow",
        )


def test_preferences_reject_invalid_saved_view() -> None:
    with pytest.raises(ValidationError):
        PreferencesUpdate(
            demandView="kanban",
            showEmptyStages=True,
            stageOrder=[],
            focusView="all",
            savedViews=[
                {
                    "id": "invalida",
                    "name": "X",
                    "companyId": "ALL",
                    "status": "UNKNOWN",
                    "priority": "ALL",
                    "focusView": "all",
                }
            ],
        )
