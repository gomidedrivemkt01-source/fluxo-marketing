"""Autenticação local por e-mail e senha, sem dependência de serviço externo.

Os hashes bcrypt migrados do Supabase Auth continuam válidos, então os usuários
existentes mantêm a senha atual.
"""

import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.models import AuthAccount, utc_now

MAX_FAILED_ATTEMPTS = 10
LOCK_DURATION = timedelta(minutes=15)
BCRYPT_MAX_BYTES = 72
TEMPORARY_PASSWORD_ALPHABET = string.ascii_letters + string.digits
TEMPORARY_PASSWORD_LENGTH = 16

# Hash fixo usado quando o e-mail não existe, para que a resposta leve o mesmo tempo.
_DUMMY_HASH = bcrypt.hashpw(b"fluxo-marketing-dummy-password", bcrypt.gensalt())


@dataclass(frozen=True, slots=True)
class AuthUser:
    id: str
    email: str
    must_change_password: bool
    metadata: dict[str, Any]


def _password_bytes(password: str) -> bytes:
    encoded = password.encode()
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ApiError(422, "password_too_long", "A senha deve ter no máximo 72 bytes.")
    return encoded


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode()


def new_temporary_password() -> str:
    return "".join(
        secrets.choice(TEMPORARY_PASSWORD_ALPHABET) for _ in range(TEMPORARY_PASSWORD_LENGTH)
    )


def _user(account: AuthAccount) -> AuthUser:
    return AuthUser(
        id=str(account.id),
        email=account.email.lower(),
        must_change_password=account.must_change_password,
        metadata=dict(account.user_metadata or {}),
    )


class LocalAuthGateway:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _by_email(self, email: str, *, lock: bool = False) -> AuthAccount | None:
        query = select(AuthAccount).where(func.lower(AuthAccount.email) == email.lower())
        if lock:
            query = query.with_for_update()
        return self.db.scalar(query)

    def register(self, email: str, password: str, metadata: dict[str, Any]) -> AuthUser:
        if self._by_email(email):
            raise ApiError(409, "email_already_registered", "Este e-mail já possui cadastro.")
        account = AuthAccount(
            id=uuid.uuid4(),
            email=email.lower(),
            password_hash=hash_password(password),
            user_metadata=metadata,
            password_changed_at=utc_now(),
        )
        self.db.add(account)
        self.db.flush()
        return _user(account)

    def login(self, email: str, password: str) -> AuthUser:
        account = self._by_email(email, lock=True)
        encoded = password.encode()
        if account is None or len(encoded) > BCRYPT_MAX_BYTES:
            bcrypt.checkpw(encoded[:BCRYPT_MAX_BYTES], _DUMMY_HASH)
            raise ApiError(400, "invalid_credentials", "E-mail ou senha inválidos.")
        now = utc_now()
        if account.locked_until and account.locked_until > now:
            raise ApiError(
                429, "too_many_attempts", "Muitas tentativas. Aguarde antes de tentar novamente."
            )
        if not bcrypt.checkpw(encoded, account.password_hash.encode()):
            account.failed_attempts += 1
            if account.failed_attempts >= MAX_FAILED_ATTEMPTS:
                account.failed_attempts = 0
                account.locked_until = now + LOCK_DURATION
            self.db.commit()
            raise ApiError(400, "invalid_credentials", "E-mail ou senha inválidos.")
        account.failed_attempts = 0
        account.locked_until = None
        self.db.flush()
        return _user(account)

    def verify_password(self, user_id: uuid.UUID, password: str) -> bool:
        account = self.db.get(AuthAccount, user_id)
        encoded = password.encode()
        if account is None or len(encoded) > BCRYPT_MAX_BYTES:
            return False
        return bcrypt.checkpw(encoded, account.password_hash.encode())

    def set_password(
        self, user_id: uuid.UUID, password: str, *, must_change: bool = False
    ) -> AuthUser:
        account = self.db.get(AuthAccount, user_id, with_for_update=True)
        if account is None:
            raise ApiError(404, "account_not_found", "Conta de acesso não encontrada.")
        account.password_hash = hash_password(password)
        account.must_change_password = must_change
        account.failed_attempts = 0
        account.locked_until = None
        account.password_changed_at = utc_now()
        self.db.flush()
        return _user(account)

    def get(self, user_id: uuid.UUID) -> AuthUser | None:
        account = self.db.get(AuthAccount, user_id)
        return _user(account) if account else None
