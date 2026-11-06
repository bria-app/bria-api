"""Companies module — presentation DI providers."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.companies.domain.enums import UserRole
from app.modules.companies.infrastructure.persistence.repositories import (
    SqlCompanyRepository,
    SqlUserRepository,
)
from app.shared.domain.errors import ValidationError
from app.shared.infrastructure.database import get_db


def get_company_repository(db: Session = Depends(get_db, scope="function")) -> SqlCompanyRepository:
    return SqlCompanyRepository(db)


def get_user_repository(db: Session = Depends(get_db, scope="function")) -> SqlUserRepository:
    return SqlUserRepository(db)


def parse_role(role: str) -> UserRole:
    """Convert a raw role string into a UserRole, raising a domain error if invalid."""
    try:
        return UserRole(role)
    except ValueError as exc:
        valid = ", ".join(r.value for r in UserRole)
        raise ValidationError(
            message=f"El rol «{role}» no existe. Elige uno de: {valid}."
        ) from exc
