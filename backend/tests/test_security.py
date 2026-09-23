from base64 import urlsafe_b64encode

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
