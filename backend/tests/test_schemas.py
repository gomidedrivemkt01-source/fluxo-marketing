import pytest
from pydantic import ValidationError

from app.auth.schemas import RegisterRequest, VerifyRequest


def test_register_requires_long_password() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            name="Pessoa Teste",
            email="pessoa@example.com",
            password="curta",
            privacyNoticeVersion="draft-1",
        )


def test_verification_code_has_exactly_six_digits() -> None:
    request = VerifyRequest(email="pessoa@example.com", code="123456", purpose="signup")
    assert request.code == "123456"
    with pytest.raises(ValidationError):
        VerifyRequest(email="pessoa@example.com", code="12345x", purpose="signup")
