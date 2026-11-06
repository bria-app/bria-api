from typing import Callable
from uuid import UUID
from fastapi import Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.shared.infrastructure.database.database import get_db
from app.shared.infrastructure.security.jwt import decode_token
from app.shared.infrastructure.security.auth import oauth2_scheme
from app.shared.presentation.schemas import PaginationParams
from app.shared.domain.errors import UnauthorizedError, ForbiddenError

# Re-export
__all__ = ["get_db", "get_pagination", "get_current_user", "require_company_access", "require_role"]

def get_pagination(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Page size")
) -> PaginationParams:
    """Dependency to get pagination parameters."""
    return PaginationParams(page=page, size=size)

class AuthenticatedUser(BaseModel):
    """Minimal representation of a user from JWT claims."""
    user_id: UUID
    company_id: UUID
    role: str

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db, scope="function"),
) -> AuthenticatedUser:
    """Dependency to get the current authenticated user from the JWT token.

    The token is re-validated against the database on every request (audit A-02): a user
    that was disabled, deleted or moved loses access at once, and the role used for
    authorization is the *current* one, not the one frozen in the token (a demoted
    admin cannot keep admin rights until the token expires). One primary-key lookup.
    """
    payload = decode_token(token)
    user_id_str = payload.get("sub")
    company_id_str = payload.get("company_id")
    role = payload.get("role")
    
    if not user_id_str or not company_id_str or not role:
        raise UnauthorizedError(message="Tu sesión no es válida. Vuelve a iniciar sesión.")
        
    try:
        user_id = UUID(user_id_str)
        company_id = UUID(company_id_str)
    except ValueError:
        raise UnauthorizedError(message="Tu sesión no es válida. Vuelve a iniciar sesión.")

    # Imported here: the shared kernel only needs the users table, and a module-level
    # import would create an import cycle with the companies module.
    from app.modules.companies.infrastructure.persistence.models import UserModel

    row = db.execute(
        select(UserModel.company_id, UserModel.role, UserModel.status).where(UserModel.id == user_id)
    ).first()
    if row is None or row.company_id != company_id or row.status == "disabled":
        raise UnauthorizedError(message="Tu sesión ya no es válida. Vuelve a iniciar sesión.")

    return AuthenticatedUser(
        user_id=user_id,
        company_id=company_id,
        role=str(row.role),
    )

# Sellers (cashiers created by the admin) only run the till: they can sell and look
# products/stock up, nothing else. Resource = first path segment after /companies/{id}.
# Writes are limited to POST on the till resources (audit A-02): ringing up a ticket and
# recording a lost sale. No DELETE /sales/{id}, no POST /sales/bulk or /sales/import,
# no invoices of their own (the till issues them through the sales order).
SELLER_WRITE_RESOURCES = frozenset({"sales-orders", "lost-sales"})
#: A viewer («Lector») only reads. The only changes it can make are its own: marking its notices
#: as read and saving its preferences (onboarding, appearance).
VIEWER_WRITE_RESOURCES = frozenset({"notifications", "preferences"})
SELLER_READ_RESOURCES = frozenset(
    {
        "", "products", "product-categories", "inventory", "custom-fields", "preferences",
        "notifications", "billing", "sales", "sales-orders", "invoices", "lost-sales",
    }
)


def require_company_access(
    company_id: UUID,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Validates that the current user has access to the requested company_id."""
    if current_user.company_id != company_id:
        raise ForbiddenError(message="No tienes acceso a esta empresa. Revisa que hayas iniciado sesión con la cuenta correcta.")
    if current_user.role == "seller":
        marker = f"/companies/{company_id}"
        path = request.url.path
        rest = path.split(marker, 1)[1].strip("/") if marker in path else ""
        resource = rest.split("/", 1)[0]
        allowed = (request.method == "POST" and resource in SELLER_WRITE_RESOURCES) or (
            request.method == "GET" and resource in SELLER_READ_RESOURCES
        )
        if not allowed:
            raise ForbiddenError(message="Tu usuario de ventas no tiene acceso a este módulo.")
    if current_user.role == "viewer" and request.method not in ("GET", "HEAD", "OPTIONS"):
        marker = f"/companies/{company_id}"
        path = request.url.path
        rest = path.split(marker, 1)[1].strip("/") if marker in path else ""
        if rest.split("/", 1)[0] not in VIEWER_WRITE_RESOURCES:
            raise ForbiddenError(message="Tu usuario es de solo lectura: pídele a un administrador que haga este cambio.")
    return current_user

def require_role(*allowed_roles: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Factory dependency to restrict access based on user role."""
    def role_checker(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if current_user.role not in allowed_roles:
            raise ForbiddenError(message=f"No tienes permiso para esta acción. Pídeselo a un usuario con rol: {', '.join(allowed_roles)}.")
        return current_user
    return role_checker
