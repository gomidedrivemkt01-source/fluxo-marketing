from fastapi import APIRouter, Depends, Response, status

from app.api.errors import ApiError
from app.auth.dependencies import (
    get_auth_gateway,
    get_principal,
    get_session_service,
    require_csrf,
)
from app.auth.local import LocalAuthGateway
from app.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    SessionResponse,
)
from app.auth.service import CSRF_COOKIE, SESSION_COOKIE, Principal, SessionIssue, SessionService
from app.core.config import Settings, get_settings
from app.models import AuditEvent

router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _set_session_cookies(response: Response, issued: SessionIssue, settings: Settings) -> None:
    max_age = 7 * 24 * 60 * 60
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=max_age,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        issued.csrf_token,
        max_age=max_age,
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")


def _session_response(principal: Principal, gateway: LocalAuthGateway) -> SessionResponse:
    account = gateway.get(principal.profile.auth_user_id)
    return SessionResponse(
        state=principal.membership.status.value,
        name=principal.profile.full_name,
        email=principal.profile.email,
        role=principal.role.code if principal.role else None,
        mustChangePassword=bool(account and account.must_change_password),
    )


@router.post("/register", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    gateway: LocalAuthGateway = Depends(get_auth_gateway),
    sessions: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    user = gateway.register(
        str(payload.email).lower(),
        payload.password,
        {
            "full_name": payload.name,
            "privacy_notice_version": payload.privacy_notice_version,
        },
    )
    profile, membership = sessions.ensure_identity(
        user, privacy_notice_version=payload.privacy_notice_version
    )
    issued = sessions.issue(profile, membership)
    _set_session_cookies(response, issued, settings)
    return _session_response(issued.principal, gateway)


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    response: Response,
    gateway: LocalAuthGateway = Depends(get_auth_gateway),
    sessions: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    user = gateway.login(str(payload.email).lower(), payload.password)
    profile, membership = sessions.ensure_identity(user, record_registration=False)
    issued = sessions.issue(profile, membership)
    _set_session_cookies(response, issued, settings)
    return _session_response(issued.principal, gateway)


@router.post(
    "/change-password", response_model=SessionResponse, dependencies=[Depends(require_csrf)]
)
def change_password(
    payload: ChangePasswordRequest,
    principal: Principal = Depends(get_principal),
    gateway: LocalAuthGateway = Depends(get_auth_gateway),
    sessions: SessionService = Depends(get_session_service),
) -> SessionResponse:
    auth_user_id = principal.profile.auth_user_id
    if not gateway.verify_password(auth_user_id, payload.current_password):
        raise ApiError(400, "invalid_current_password", "A senha atual não confere.")
    if payload.current_password == payload.password:
        raise ApiError(422, "password_unchanged", "Escolha uma senha diferente da atual.")
    gateway.set_password(auth_user_id, payload.password)
    sessions.revoke_other_sessions(principal)
    sessions.db.add(
        AuditEvent(
            organization_id=principal.membership.organization_id,
            actor_user_id=principal.profile.id,
            event_type="PASSWORD_CHANGED",
            metadata_json={},
        )
    )
    sessions.db.commit()
    return _session_response(principal, gateway)


@router.get("/session", response_model=SessionResponse)
def current_session(
    principal: Principal = Depends(get_principal),
    gateway: LocalAuthGateway = Depends(get_auth_gateway),
) -> SessionResponse:
    return _session_response(principal, gateway)


@router.post("/logout", response_model=MessageResponse, dependencies=[Depends(require_csrf)])
def logout(
    response: Response,
    principal: Principal = Depends(get_principal),
    sessions: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    sessions.revoke(principal)
    _clear_session_cookies(response, settings)
    return MessageResponse(message="Sessão encerrada.")


@router.post("/logout-all", response_model=MessageResponse, dependencies=[Depends(require_csrf)])
def logout_all(
    response: Response,
    principal: Principal = Depends(get_principal),
    sessions: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    sessions.revoke(principal, all_sessions=True)
    _clear_session_cookies(response, settings)
    return MessageResponse(message="Todas as sessões foram encerradas.")
