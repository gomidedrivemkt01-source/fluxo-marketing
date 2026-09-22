from fastapi import APIRouter, Depends, Response, status

from app.auth.dependencies import (
    get_auth_gateway,
    get_principal,
    get_session_service,
    require_csrf,
)
from app.auth.schemas import (
    EmailRequest,
    LoginRequest,
    MessageResponse,
    RecoveryResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionResponse,
    VerifyRequest,
)
from app.auth.service import CSRF_COOKIE, SESSION_COOKIE, Principal, SessionIssue, SessionService
from app.auth.supabase import SupabaseAuthGateway
from app.core.config import Settings, get_settings

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


def _session_response(principal: Principal) -> SessionResponse:
    return SessionResponse(
        state=principal.membership.status.value,
        name=principal.profile.full_name,
        email=principal.profile.email,
        role=principal.role.code if principal.role else None,
    )


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def register(
    payload: RegisterRequest,
    gateway: SupabaseAuthGateway = Depends(get_auth_gateway),
) -> MessageResponse:
    await gateway.register(
        str(payload.email).lower(),
        payload.password,
        {
            "full_name": payload.name,
            "privacy_notice_version": payload.privacy_notice_version,
        },
    )
    return MessageResponse(message="Enviamos um código para confirmar o e-mail.")


@router.post("/verify-email", response_model=SessionResponse | RecoveryResponse)
async def verify_email(
    payload: VerifyRequest,
    response: Response,
    gateway: SupabaseAuthGateway = Depends(get_auth_gateway),
    sessions: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> SessionResponse | RecoveryResponse:
    tokens = await gateway.verify(str(payload.email).lower(), payload.code, payload.purpose)
    if payload.purpose == "recovery":
        return RecoveryResponse(recoveryToken=sessions.recovery_token(tokens.access_token))
    profile, membership = sessions.ensure_identity(
        tokens,
        privacy_notice_version=str(tokens.user.metadata.get("privacy_notice_version") or ""),
    )
    issued = sessions.issue(tokens, profile, membership)
    _set_session_cookies(response, issued, settings)
    return _session_response(issued.principal)


@router.post("/login", response_model=SessionResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    gateway: SupabaseAuthGateway = Depends(get_auth_gateway),
    sessions: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    tokens = await gateway.login(str(payload.email).lower(), payload.password)
    profile, membership = sessions.ensure_identity(tokens, record_verification=False)
    issued = sessions.issue(tokens, profile, membership)
    _set_session_cookies(response, issued, settings)
    return _session_response(issued.principal)


@router.post("/forgot-password", response_model=MessageResponse, status_code=202)
async def forgot_password(
    payload: EmailRequest,
    gateway: SupabaseAuthGateway = Depends(get_auth_gateway),
) -> MessageResponse:
    try:
        await gateway.request_recovery(str(payload.email).lower())
    except Exception:
        # Mantém resposta uniforme para não revelar se uma conta existe.
        pass
    return MessageResponse(message="Se a conta existir, enviaremos um código de recuperação.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    gateway: SupabaseAuthGateway = Depends(get_auth_gateway),
    sessions: SessionService = Depends(get_session_service),
) -> MessageResponse:
    access_token = sessions.consume_recovery_token(payload.recovery_token)
    user = await gateway.reset_password(access_token, payload.password)
    profile = sessions.profile_by_auth_user_id(user.id)
    if profile:
        sessions.revoke_profile_sessions(profile.id)
    return MessageResponse(message="Senha alterada. Faça login novamente.")


@router.get("/session", response_model=SessionResponse)
def current_session(principal: Principal = Depends(get_principal)) -> SessionResponse:
    return _session_response(principal)


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
