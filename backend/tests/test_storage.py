import httpx
import pytest

from app.api.errors import ApiError
from app.storage import StorageAuthenticationError, SupabaseStorageGateway


def response(status_code: int, payload: dict[str, str]) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=httpx.Request("POST", "https://storage"))


@pytest.mark.parametrize("status_code", [400, 401])
def test_invalid_jwt_requests_token_refresh(status_code: int) -> None:
    with pytest.raises(StorageAuthenticationError):
        SupabaseStorageGateway._raise_for_status(
            response(status_code, {"code": "InvalidJWT", "message": "The token has expired."})
        )


def test_expired_claim_requests_token_refresh() -> None:
    with pytest.raises(StorageAuthenticationError):
        SupabaseStorageGateway._raise_for_status(
            response(
                400,
                {
                    "code": "AccessDenied",
                    "message": '"exp" claim timestamp check failed',
                },
            )
        )


def test_generic_bad_request_is_not_mistaken_for_expired_session() -> None:
    with pytest.raises(ApiError) as caught:
        SupabaseStorageGateway._raise_for_status(
            response(400, {"code": "InvalidRequest", "message": "Missing Content-Length"})
        )
    assert caught.value.status_code == 502
