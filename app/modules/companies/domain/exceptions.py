"""Companies module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import ConflictError, NotFoundError, ValidationError


class CompanyNotFoundError(NotFoundError):
    def __init__(self, company_id: UUID) -> None:
        super().__init__(
            message="No encontramos la empresa. Actualiza la página e inténtalo de nuevo.",
            details={"company_id": str(company_id)},
        )


class CompanyAlreadyExistsError(ConflictError):
    def __init__(self, tax_id: str) -> None:
        super().__init__(
            message=f"Ya hay una empresa registrada con el RUC {tax_id}. Inicia sesión o usa otro RUC.",
            details={"tax_id": tax_id},
        )


class UserNotFoundError(NotFoundError):
    def __init__(self, identifier: str) -> None:
        super().__init__(
            message="No encontramos ese usuario. Actualiza la página e inténtalo de nuevo.",
            details={"identifier": identifier},
        )


class UserAlreadyExistsError(ConflictError):
    def __init__(self, email: str) -> None:
        super().__init__(
            message=f"Ya existe un usuario con el correo {email}. Inicia sesión o usa otro correo.",
            details={"email": email},
        )


class UsernameAlreadyExistsError(ConflictError):
    def __init__(self, username: str) -> None:
        super().__init__(
            message=f"El usuario '{username}' ya existe. Elige otro.",
            details={"username": username},
        )


class InvalidCompanyStateError(ValidationError):
    pass


class InvalidUserStateError(ValidationError):
    pass


class WeakPasswordError(InvalidUserStateError):
    """A new password shorter than the minimum (audit: same rule as the web, 8 characters)."""

    def __init__(self, min_length: int, length: int, field: str = "password") -> None:
        super().__init__(
            message=(
                f"La contraseña debe tener al menos {min_length} caracteres "
                f"(escribiste {length}). Usa una más larga."
            ),
            details={"field": field, "min_length": min_length},
        )
