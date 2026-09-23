from base64 import urlsafe_b64encode

from app.core.config import Settings
from app.core.security import TokenCipher, hash_session_token, new_session_token


def test_session_tokens_are_random_and_hash_is_stable() -> None:
    first = new_session_token()
    second = new_session_token()
    assert first != second
    assert len(first) >= 48
    assert hash_session_token(first, "secret") == hash_session_token(first, "secret")
    assert hash_session_token(first, "secret") != hash_session_token(second, "secret")


def test_token_cipher_round_trip_and_rejects_tampering() -> None:
    cipher = TokenCipher(urlsafe_b64encode(b"0" * 32).decode())
    encrypted = cipher.encrypt("access-token")
    assert encrypted != "access-token"
    assert cipher.decrypt(encrypted) == "access-token"
    try:
        cipher.decrypt(encrypted[:-2] + "xx")
    except ValueError:
        pass
    else:
        raise AssertionError("Token adulterado deveria falhar")


def test_token_cipher_derives_fernet_key_from_random_secret() -> None:
    cipher = TokenCipher("render-generated-random-secret-with-more-than-32-characters")
    encrypted = cipher.encrypt("refresh-token")
    assert cipher.decrypt(encrypted) == "refresh-token"


def test_database_dsn_encodes_separate_secret_fields() -> None:
    settings = Settings(
        database_url=None,
        database_host="pooler.example.com",
        database_user="postgres.project",
        database_password="p@ss:word/with symbols",
        session_secret="session-secret-with-more-than-thirty-two-characters",
        token_encryption_key="encryption-secret-with-more-than-thirty-two-characters",
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="test-key",
    )
    assert settings.database_dsn() == (
        "postgresql+psycopg://postgres.project:p%40ss%3Aword%2Fwith%20symbols@"
        "pooler.example.com:5432/postgres?sslmode=require"
    )
