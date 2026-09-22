from dataclasses import dataclass
from typing import Any

import httpx

from app.api.errors import ApiError


@dataclass(frozen=True, slots=True)
class AuthUser:
    id: str
    email: str
    email_confirmed: bool
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user: AuthUser


class SupabaseAuthGateway:
    def __init__(self, base_url: str, publishable_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"apikey": publishable_key, "Content-Type": "application/json"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        headers = dict(self._headers)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(
                    method, f"{self._base_url}/auth/v1{path}", headers=headers, json=body
                )
        except httpx.RequestError as exc:
            raise ApiError(
                503, "auth_unavailable", "O serviço de acesso está indisponível."
            ) from exc
        if response.status_code >= 400:
            detail = (
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            code = detail.get("error_code") or detail.get("code") or "auth_failed"
            if code in {"invalid_credentials", "email_not_confirmed"}:
                message = "E-mail ou senha inválidos."
            elif code in {"otp_expired", "token_expired"}:
                message = "O código expirou. Solicite um novo."
            elif response.status_code == 429:
                message = "Muitas tentativas. Aguarde antes de tentar novamente."
            else:
                message = "Não foi possível concluir a autenticação."
            raise ApiError(429 if response.status_code == 429 else 400, str(code), message)
        return response.json() if response.content else {}

    @staticmethod
    def _user(data: dict[str, Any]) -> AuthUser:
        confirmed = bool(data.get("email_confirmed_at") or data.get("confirmed_at"))
        return AuthUser(
            id=str(data["id"]),
            email=str(data.get("email", "")).lower(),
            email_confirmed=confirmed,
            metadata=dict(data.get("user_metadata") or {}),
        )

    @classmethod
    def _tokens(cls, data: dict[str, Any]) -> AuthTokens:
        return AuthTokens(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            expires_in=int(data.get("expires_in", 3600)),
            user=cls._user(dict(data["user"])),
        )

    async def register(self, email: str, password: str, metadata: dict[str, Any]) -> None:
        await self._request(
            "POST", "/signup", body={"email": email, "password": password, "data": metadata}
        )

    async def verify(self, email: str, token: str, purpose: str) -> AuthTokens:
        data = await self._request(
            "POST", "/verify", body={"email": email, "token": token, "type": purpose}
        )
        return self._tokens(data)

    async def login(self, email: str, password: str) -> AuthTokens:
        data = await self._request(
            "POST", "/token?grant_type=password", body={"email": email, "password": password}
        )
        return self._tokens(data)

    async def request_recovery(self, email: str) -> None:
        await self._request("POST", "/recover", body={"email": email})

    async def reset_password(self, access_token: str, password: str) -> AuthUser:
        data = await self._request(
            "PUT", "/user", body={"password": password}, access_token=access_token
        )
        await self._request("POST", "/logout?scope=global", access_token=access_token)
        return self._user(data)

    async def logout(self, access_token: str) -> None:
        await self._request("POST", "/logout", access_token=access_token)
