"""Companies module — use cases for the User aggregate."""
from __future__ import annotations

from uuid import UUID

from app.modules.companies.application.dtos import UserDTO
from app.modules.companies.domain.credentials import (  # MIN_PASSWORD_LENGTH: re-exported
    MIN_PASSWORD_LENGTH,  # noqa: F401
    ensure_new_password,
    normalize_email,
)
from app.modules.companies.domain.entities import User
from app.modules.companies.domain.enums import UserRole, UserStatus
from app.modules.companies.domain.exceptions import (
    InvalidUserStateError,
    UserAlreadyExistsError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from app.modules.companies.domain.repositories import UserRepository
from app.shared.domain.errors import ForbiddenError
from app.shared.domain.value_objects import Email
from app.shared.infrastructure.security.hashing import hash_password

#: Roles an owner/admin may assign. "owner" is never assignable: ownership is not
#: transferable through this endpoint (it would let an admin promote itself).
ASSIGNABLE_ROLES = frozenset({UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER, UserRole.SELLER})


def _manageable_user(
    users: UserRepository, company_id: UUID, user_id: UUID, acting_user_id: UUID
) -> User:
    """A user of ``company_id`` that ``acting_user_id`` may change (audit C-02).

    Another company's user is reported as missing (404, no existence leak); nobody can
    change their own role/status here, and the owner cannot be changed by anyone.
    """
    user = users.get_by_id(user_id)
    if user is None or user.company_id != company_id:
        raise UserNotFoundError(str(user_id))
    if user.id == acting_user_id:
        raise ForbiddenError(message="No puedes cambiar el rol ni el estado de tu propio usuario")
    if user.role == UserRole.OWNER:
        raise ForbiddenError(message="El propietario de la cuenta no se puede modificar")
    return user


class InviteUser:
    """Creates a user in INVITED state with a (temporary) hashed password."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(
        self,
        company_id: UUID,
        *,
        email: str,
        full_name: str,
        role: UserRole,
        temporary_password: str,
    ) -> UserDTO:
        email = normalize_email(email)
        ensure_new_password(temporary_password, "temporary_password")
        if self._users.get_by_email(email) is not None:
            raise UserAlreadyExistsError(email)
        user = User(
            company_id=company_id,
            email=Email(email),
            full_name=full_name,
            hashed_password=hash_password(temporary_password),
            role=role,
            status=UserStatus.INVITED,
        )
        return UserDTO.from_entity(self._users.add(user))


class CreateCompanyUser:
    """An owner/admin creates a user that signs in with a username (e.g. a seller)."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(
        self,
        company_id: UUID,
        *,
        full_name: str,
        username: str,
        password: str,
        role: UserRole,
    ) -> UserDTO:
        if role not in (UserRole.SELLER, UserRole.ADMIN):
            raise InvalidUserStateError(message="Solo se pueden crear usuarios vendedor o administrador")
        ensure_new_password(password)
        normalized = username.strip().lower()
        if self._users.get_by_username(normalized) is not None:
            raise UsernameAlreadyExistsError(normalized)
        user = User(
            company_id=company_id,
            email=None,
            username=normalized,
            full_name=full_name.strip(),
            hashed_password=hash_password(password),
            role=role,
            status=UserStatus.ACTIVE,
        )
        return UserDTO.from_entity(self._users.add(user))


class UpdateCompanyUser:
    """Rename, reset the password, or enable/disable a user of the same company."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(
        self,
        company_id: UUID,
        user_id: UUID,
        *,
        acting_user_id: UUID,
        full_name: str | None = None,
        password: str | None = None,
        status: UserStatus | None = None,
    ) -> UserDTO:
        user = self._users.get_by_id(user_id)
        if user is None or user.company_id != company_id:
            raise UserNotFoundError(str(user_id))
        if full_name is not None:
            if not full_name.strip():
                raise InvalidUserStateError(message="El nombre completo es obligatorio")
            user.full_name = full_name.strip()
        if password is not None:
            # Nobody else resets the owner's password: that would hand over the whole account.
            if user.role == UserRole.OWNER and user.id != acting_user_id:
                raise ForbiddenError(message="Solo el propietario puede cambiar su propia contraseña")
            ensure_new_password(password)
            user.hashed_password = hash_password(password)
        if status is not None and status != user.status:
            if user.id == acting_user_id:
                raise InvalidUserStateError(message="No puedes cambiar el estado de tu propio usuario")
            if user.role == UserRole.OWNER:
                raise InvalidUserStateError(message="El propietario de la cuenta no se puede desactivar")
            if status == UserStatus.DISABLED:
                user.disable()
            elif status == UserStatus.ACTIVE:
                user.activate()
            else:
                raise InvalidUserStateError(message="Ese estado no es válido. Elige activo o inactivo.")
        return UserDTO.from_entity(self._users.update(user))


class ListCompanyUsers:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[UserDTO]:
        return [
            UserDTO.from_entity(u)
            for u in self._users.list_by_company(company_id, offset, limit)
        ]


class UpdateUserRole:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(
        self, company_id: UUID, user_id: UUID, *, role: UserRole, acting_user_id: UUID
    ) -> UserDTO:
        if role not in ASSIGNABLE_ROLES:
            raise ForbiddenError(
                message="Ese rol no está permitido. Elige administrador, analista, lector o vendedor."
            )
        user = _manageable_user(self._users, company_id, user_id, acting_user_id)
        user.role = role
        return UserDTO.from_entity(self._users.update(user))


class DisableUser:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self, company_id: UUID, user_id: UUID, *, acting_user_id: UUID) -> UserDTO:
        user = _manageable_user(self._users, company_id, user_id, acting_user_id)
        user.disable()
        return UserDTO.from_entity(self._users.update(user))
