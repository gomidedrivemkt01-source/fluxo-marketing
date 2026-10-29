import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import bcrypt
import pytest
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.local import (
    MAX_FAILED_ATTEMPTS,
    LocalAuthGateway,
    hash_password,
    new_temporary_password,
)
from app.models import AuthAccount, utc_now

PASSWORD = "uma-frase-longa-e-segura"


def _account(password: str = PASSWORD, **values: object) -> AuthAccount:
    account = AuthAccount(
        id=uuid.uuid4(),
        email="Pessoa@Empresa.com",
        password_hash=hash_password(password),
        user_metadata={"full_name": "Pessoa"},
        must_change_password=False,
        failed_attempts=0,
    )
    for key, value in values.items():
        setattr(account, key, value)
    return account


def _gateway(account: AuthAccount | None) -> tuple[LocalAuthGateway, MagicMock]:
    db = MagicMock(spec=Session)
    db.scalar.return_value = account
    db.get.return_value = account
    return LocalAuthGateway(db), db


def test_login_accepts_hash_migrated_from_supabase() -> None:
    # O GoTrue grava bcrypt com prefixo $2a$ e custo 10.
    migrated = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=10, prefix=b"2a")).decode()
    gateway, _ = _gateway(_account(password_hash=migrated))
    user = gateway.login("pessoa@empresa.com", PASSWORD)
    assert user.email == "pessoa@empresa.com"
    assert user.metadata == {"full_name": "Pessoa"}


def test_wrong_password_and_unknown_email_share_the_same_error() -> None:
    gateway, _ = _gateway(_account())
    with pytest.raises(ApiError) as wrong:
        gateway.login("pessoa@empresa.com", "senha-errada-qualquer")
    gateway, _ = _gateway(None)
    with pytest.raises(ApiError) as unknown:
        gateway.login("ninguem@empresa.com", PASSWORD)
    assert wrong.value.code == unknown.value.code == "invalid_credentials"


def test_repeated_failures_lock_the_account_temporarily() -> None:
    account = _account(failed_attempts=MAX_FAILED_ATTEMPTS - 1)
    gateway, _ = _gateway(account)
    with pytest.raises(ApiError):
        gateway.login("pessoa@empresa.com", "senha-errada-qualquer")
    assert account.locked_until is not None
    with pytest.raises(ApiError) as locked:
        gateway.login("pessoa@empresa.com", PASSWORD)
    assert locked.value.status_code == 429


def test_expired_lock_allows_login_and_resets_counter() -> None:
    account = _account(failed_attempts=3, locked_until=utc_now() - timedelta(minutes=1))
    gateway, _ = _gateway(account)
    gateway.login("pessoa@empresa.com", PASSWORD)
    assert account.failed_attempts == 0
    assert account.locked_until is None


def test_register_rejects_duplicate_email() -> None:
    gateway, _ = _gateway(_account())
    with pytest.raises(ApiError) as caught:
        gateway.register("pessoa@empresa.com", PASSWORD, {})
    assert caught.value.status_code == 409


def test_register_stores_only_the_hash() -> None:
    gateway, db = _gateway(None)
    user = gateway.register("Nova@Empresa.com", PASSWORD, {"full_name": "Nova"})
    stored = db.add.call_args.args[0]
    assert isinstance(stored, AuthAccount)
    assert stored.email == user.email == "nova@empresa.com"
    assert PASSWORD not in stored.password_hash
    assert bcrypt.checkpw(PASSWORD.encode(), stored.password_hash.encode())


def test_temporary_password_forces_change_and_unlocks() -> None:
    account = _account(failed_attempts=4, locked_until=utc_now() + timedelta(minutes=5))
    gateway, _ = _gateway(account)
    temporary = new_temporary_password()
    user = gateway.set_password(account.id, temporary, must_change=True)
    assert user.must_change_password
    assert account.locked_until is None
    assert gateway.verify_password(account.id, temporary)
    assert not gateway.verify_password(account.id, PASSWORD)


def test_passwords_over_bcrypt_limit_are_rejected() -> None:
    with pytest.raises(ApiError) as caught:
        hash_password("á" * 40)
    assert caught.value.code == "password_too_long"
