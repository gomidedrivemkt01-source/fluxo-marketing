from app.api.errors import ApiError
from app.auth.service import Principal
from app.models import MembershipStatus


def require_active(principal: Principal) -> None:
    if principal.membership.status == MembershipStatus.SUSPENDED:
        raise ApiError(403, "account_suspended", "Seu acesso está suspenso.")
    if principal.membership.status != MembershipStatus.ACTIVE or not principal.role:
        raise ApiError(403, "approval_required", "Seu cadastro aguarda liberação.")


def require_permission(principal: Principal, permission: str) -> None:
    require_active(principal)
    permissions = set(principal.role.permissions if principal.role else [])
    if "*" not in permissions and permission not in permissions:
        raise ApiError(403, "permission_denied", "Você não tem permissão para esta ação.")
