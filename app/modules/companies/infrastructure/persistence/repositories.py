"""Companies module — SQLAlchemy repository implementations of the domain ports."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.companies.domain.entities import Company, User
from app.modules.companies.domain.exceptions import (
    CompanyNotFoundError,
    UserNotFoundError,
)
from app.modules.companies.infrastructure.persistence.mappers import (
    company_to_entity,
    company_to_model,
    user_to_entity,
    user_to_model,
)
from app.modules.companies.infrastructure.persistence.models import (
    CompanyModel,
    UserModel,
)


class SqlCompanyRepository:
    """SQLAlchemy implementation of CompanyRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, company_id: UUID) -> Company | None:
        model = self._session.get(CompanyModel, company_id)
        return company_to_entity(model) if model else None

    def get_by_tax_id(self, tax_id: str) -> Company | None:
        model = self._session.execute(
            select(CompanyModel).where(CompanyModel.tax_id == tax_id)
        ).scalar_one_or_none()
        return company_to_entity(model) if model else None

    def list(self, offset: int = 0, limit: int = 50) -> list[Company]:
        rows = self._session.execute(
            select(CompanyModel).order_by(CompanyModel.created_at).offset(offset).limit(limit)
        ).scalars().all()
        return [company_to_entity(m) for m in rows]

    def add(self, company: Company) -> Company:
        model = company_to_model(company)
        self._session.add(model)
        self._session.flush()
        return company_to_entity(model)

    def update(self, company: Company) -> Company:
        model = self._session.get(CompanyModel, company.id)
        if model is None:
            raise CompanyNotFoundError(company.id)  # type: ignore[arg-type]
        model.name = company.name
        model.tax_id = company.tax_id
        model.business_type = company.business_type
        model.address = company.address
        model.phone = company.phone
        model.email = company.email.value
        model.plan = company.plan.value
        model.status = company.status.value
        self._session.flush()
        return company_to_entity(model)

    def delete(self, company_id: UUID) -> bool:
        model = self._session.get(CompanyModel, company_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True


class SqlUserRepository:
    """SQLAlchemy implementation of UserRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: UUID) -> User | None:
        model = self._session.get(UserModel, user_id)
        return user_to_entity(model) if model else None

    def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        if not normalized:
            return None
        model = self._session.execute(
            select(UserModel).where(UserModel.email == normalized)
        ).scalar_one_or_none()
        if model is None:
            # Rows written before emails were normalised may keep capitals or spaces:
            # compare the normalised form so they are still found (and never duplicated).
            model = self._session.execute(
                select(UserModel)
                .where(func.lower(func.trim(UserModel.email)) == normalized)
                .order_by(UserModel.created_at)
                .limit(1)
            ).scalar_one_or_none()
        return user_to_entity(model) if model else None

    def get_by_username(self, username: str) -> User | None:
        normalized = username.strip().lower()
        model = self._session.execute(
            select(UserModel).where(UserModel.username == normalized)
        ).scalar_one_or_none()
        return user_to_entity(model) if model else None

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[User]:
        rows = self._session.execute(
            select(UserModel)
            .where(UserModel.company_id == company_id)
            .order_by(UserModel.created_at)
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return [user_to_entity(m) for m in rows]

    def add(self, user: User) -> User:
        model = user_to_model(user)
        self._session.add(model)
        self._session.flush()
        return user_to_entity(model)

    def update(self, user: User) -> User:
        model = self._session.get(UserModel, user.id)
        if model is None:
            raise UserNotFoundError(str(user.id))
        model.company_id = user.company_id
        model.email = user.email.value if user.email else None
        model.username = user.username
        model.full_name = user.full_name
        model.hashed_password = user.hashed_password
        model.role = user.role.value
        model.status = user.status.value
        model.last_login_at = user.last_login_at
        self._session.flush()
        return user_to_entity(model)

    def delete(self, user_id: UUID) -> bool:
        model = self._session.get(UserModel, user_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True
