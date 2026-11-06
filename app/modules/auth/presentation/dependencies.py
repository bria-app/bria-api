"""Auth module — presentation DI providers.

Reuses the companies persistence repositories (auth has no entity of its own).
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.companies.infrastructure.persistence.repositories import (
    SqlCompanyRepository,
    SqlUserRepository,
)
from app.shared.infrastructure.database import get_db


def get_company_repository(db: Session = Depends(get_db, scope="function")) -> SqlCompanyRepository:
    return SqlCompanyRepository(db)


def get_user_repository(db: Session = Depends(get_db, scope="function")) -> SqlUserRepository:
    return SqlUserRepository(db)
