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


def test_verification_code_accepts_six_to_eight_digits() -> None:
    six_digits = VerifyRequest(email="pessoa@example.com", code="123456", purpose="signup")
    eight_digits = VerifyRequest(email="pessoa@example.com", code="12345678", purpose="signup")
    assert six_digits.code == "123456"
    assert eight_digits.code == "12345678"
    with pytest.raises(ValidationError):
        VerifyRequest(email="pessoa@example.com", code="12345", purpose="signup")
    with pytest.raises(ValidationError):
        VerifyRequest(email="pessoa@example.com", code="12345x", purpose="signup")
