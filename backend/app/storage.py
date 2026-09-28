from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.api.errors import ApiError


class StorageAuthenticationError(Exception):
    """The Supabase user token must be refreshed before retrying."""


class SupabaseStorageGateway:
    def __init__(self, base_url: str, publishable_key: str, bucket: str) -> None:
        self._root = f"{base_url.rstrip('/')}/storage/v1"
        self._publishable_key = publishable_key
        self.bucket = bucket

    def _headers(self, access_token: str, **extra: str) -> dict[str, str]:
        return {
            "apikey": self._publishable_key,
            "Authorization": f"Bearer {access_token}",
            **extra,
        }

    @staticmethod
    def _error_details(response: httpx.Response) -> tuple[str, str]:
        try:
            payload = response.json()
        except ValueError:
            return "", ""
        if not isinstance(payload, dict):
            return "", ""
        code = str(payload.get("code") or payload.get("errorCode") or "")
        message = str(payload.get("message") or payload.get("error") or "")
        return code, message

    @classmethod
    def _raise_for_status(cls, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        code, raw_message = cls._error_details(response)
        normalized_code = code.lower()
        message = raw_message.lower()
        if response.status_code == 401 or normalized_code in {"invalidjwt", "expiredtoken"}:
            raise StorageAuthenticationError
        if response.status_code == 404:
            raise ApiError(404, "file_object_not_found", "O arquivo não está disponível.")
        if response.status_code == 409 or "already exists" in message:
            raise ApiError(409, "file_object_conflict", "Já existe um arquivo neste caminho.")
        if response.status_code == 413:
            raise ApiError(413, "file_too_large", "O arquivo excede o limite permitido.")
        if response.status_code == 403:
            raise ApiError(403, "file_storage_denied", "O Storage recusou o acesso ao arquivo.")
        raise ApiError(502, "file_storage_failed", "O Storage não conseguiu processar o arquivo.")

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = await client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise ApiError(
                503, "file_storage_unavailable", "O serviço de arquivos está indisponível."
            ) from exc
        self._raise_for_status(response)
        return response

    def _object_url(self, path: str) -> str:
        return f"{self._root}/object/{quote(self.bucket, safe='')}/{quote(path, safe='/')}"

    async def upload(
        self,
        path: str,
        data: bytes,
        content_type: str,
        access_token: str,
    ) -> None:
        await self._request(
            "POST",
            self._object_url(path),
            headers=self._headers(
                access_token,
                **{"Content-Type": content_type},
            ),
            content=data,
        )

    async def remove(self, path: str, access_token: str) -> None:
        await self._request(
            "DELETE",
            f"{self._root}/object/{quote(self.bucket, safe='')}",
            headers=self._headers(access_token, **{"Content-Type": "application/json"}),
            json={"prefixes": [path]},
        )

    async def create_signed_url(
        self,
        path: str,
        access_token: str,
        expires_in: int,
        download_name: str,
    ) -> str:
        response = await self._request(
            "POST",
            f"{self._root}/object/sign/{quote(self.bucket, safe='')}/{quote(path, safe='/')}",
            headers=self._headers(access_token, **{"Content-Type": "application/json"}),
            json={"expiresIn": expires_in},
        )
        payload = response.json()
        signed_path = str(payload.get("signedURL") or payload.get("signedUrl") or "")
        if not signed_path:
            raise ApiError(502, "file_sign_failed", "Não foi possível preparar o download.")
        separator = "&" if "?" in signed_path else "?"
        return f"{self._root}{signed_path}{separator}{urlencode({'download': download_name})}"
