"""Companies module domain — entities."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.modules.companies.domain.enums import (
    CompanyPlan,
    CompanyStatus,
    UserRole,
    UserStatus,
)
from app.modules.companies.domain.exceptions import (
    InvalidCompanyStateError,
    InvalidUserStateError,
)
from app.shared.domain.errors import ValidationError
from app.shared.domain.value_objects import Email


# Role-permission mapping (domain knowledge)
_ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.OWNER: frozenset({"read", "write", "delete", "analyze", "manage"}),
    UserRole.ADMIN: frozenset({"read", "write", "delete", "analyze", "manage"}),
    UserRole.ANALYST: frozenset({"read", "analyze"}),
    UserRole.VIEWER: frozenset({"read"}),
    UserRole.SELLER: frozenset({"read", "write"}),  # scoped to sales by require_company_access
}

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,60}$")


@dataclass
class Company:
    """Represents a company (tenant) in the system."""

    name: str
    tax_id: str
    business_type: str
    address: str
    phone: str
    email: Email
    plan: CompanyPlan = CompanyPlan.FREE
    status: CompanyStatus = CompanyStatus.ACTIVE
    id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError(message="Escribe el nombre de la empresa.")
        if not self.tax_id.strip():
            raise ValidationError(message="Escribe el RUC de la empresa.")

    def suspend(self) -> None:
        """Suspend this company."""
        if self.status == CompanyStatus.SUSPENDED:
            raise InvalidCompanyStateError(
                message="La empresa ya está suspendida."
            )
        self.status = CompanyStatus.SUSPENDED

    def activate(self) -> None:
        """Activate this company."""
        if self.status == CompanyStatus.ACTIVE:
            raise InvalidCompanyStateError(
                message="La empresa ya está activa."
            )
        self.status = CompanyStatus.ACTIVE


@dataclass
class User:
    """Represents a user belonging to a company."""

    company_id: UUID
    email: Email | None
    full_name: str
    hashed_password: str
    role: UserRole = UserRole.VIEWER
    status: UserStatus = UserStatus.INVITED
    last_login_at: datetime | None = None
    # Owners sign in with email; sellers created by an admin sign in with a username.
    username: str | None = None
    id: UUID | None = None

    def __post_init__(self) -> None:
        if self.username is not None:
            self.username = self.username.strip().lower()
            if not USERNAME_RE.match(self.username):
                raise ValidationError(
                    message="El usuario debe tener 3 a 60 caracteres: letras minúsculas, números, punto, guion o guion bajo."
                )
        if self.email is None and not self.username:
            raise ValidationError(message="El usuario necesita un correo o un nombre de usuario")
        if not self.full_name.strip():
            raise ValidationError(message="El nombre completo es obligatorio")

    @property
    def login(self) -> str:
        """The identifier the user signs in with."""
        return self.username or (self.email.value if self.email else "")

    def can(self, permission: str) -> bool:
        """Check whether the user's role grants the given permission."""
        return permission in _ROLE_PERMISSIONS.get(self.role, frozenset())

    def disable(self) -> None:
        """Disable this user account."""
        if self.status == UserStatus.DISABLED:
            raise InvalidUserStateError(
                message="Este usuario ya está desactivado."
            )
        self.status = UserStatus.DISABLED

    def activate(self) -> None:
        """Re-enable a disabled (or invited) user."""
        if self.status == UserStatus.ACTIVE:
            raise InvalidUserStateError(message="Este usuario ya está activo.")
        self.status = UserStatus.ACTIVE

    def record_login(self) -> None:
        """Record the current time as the last login."""
        self.last_login_at = datetime.now(timezone.utc)
