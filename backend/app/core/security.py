import hashlib
import hmac
import secrets
from base64 import urlsafe_b64encode

from cryptography.fernet import Fernet, InvalidToken


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


class TokenCipher:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode())
        except ValueError:
            derived_key = urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
            self._fernet = Fernet(derived_key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str, *, ttl: int | None = None) -> str:
        try:
            return self._fernet.decrypt(value.encode(), ttl=ttl).decode()
        except InvalidToken as exc:
            raise ValueError("Stored token could not be decrypted") from exc
