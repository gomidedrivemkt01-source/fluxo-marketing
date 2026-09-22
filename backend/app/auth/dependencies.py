import hmac

from fastapi import Cookie, Depends, Header
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.service import CSRF_COOKIE, SESSION_COOKIE, Principal, SessionService
from app.auth.supabase import SupabaseAuthGateway
from app.core.config import Settings, get_settings
from app.database import get_db


def get_auth_gateway(settings: Settings = Depends(get_settings)) -> SupabaseAuthGateway:
    return SupabaseAuthGateway(
        str(settings.supabase_url), settings.supabase_publishable_key.get_secret_value()
    )


def get_session_service(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> SessionService:
    return SessionService(db, settings)


def get_principal(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    service: SessionService = Depends(get_session_service),
) -> Principal:
    return service.principal(session_token)


def require_csrf(
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
        raise ApiError(403, "csrf_failed", "A solicitação não pôde ser validada.")
