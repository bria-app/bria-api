"""Companies module — mappers between ORM models and domain entities."""
from __future__ import annotations

from app.modules.companies.domain.entities import Company, User
from app.modules.companies.domain.enums import (
    CompanyPlan,
    CompanyStatus,
    UserRole,
    UserStatus,
)
from app.modules.companies.infrastructure.persistence.models import (
    CompanyModel,
    UserModel,
)
from app.shared.domain.value_objects import Email


def company_to_entity(model: CompanyModel) -> Company:
    return Company(
        id=model.id,
        name=model.name,
        tax_id=model.tax_id,
        business_type=model.business_type,
        address=model.address,
        phone=model.phone,
        email=Email(model.email),
        plan=CompanyPlan(model.plan),
        status=CompanyStatus(model.status),
    )


def company_to_model(entity: Company) -> CompanyModel:
    return CompanyModel(
        id=entity.id,
        name=entity.name,
        tax_id=entity.tax_id,
        business_type=entity.business_type,
        address=entity.address,
        phone=entity.phone,
        email=entity.email.value,
        plan=entity.plan.value,
        status=entity.status.value,
    )


def user_to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        company_id=model.company_id,
        email=Email(model.email) if model.email else None,
        username=model.username,
        full_name=model.full_name,
        hashed_password=model.hashed_password,
        role=UserRole(model.role),
        status=UserStatus(model.status),
        last_login_at=model.last_login_at,
    )


def user_to_model(entity: User) -> UserModel:
    return UserModel(
        id=entity.id,
        company_id=entity.company_id,
        email=entity.email.value if entity.email else None,
        username=entity.username,
        full_name=entity.full_name,
        hashed_password=entity.hashed_password,
        role=entity.role.value,
        status=entity.status.value,
        last_login_at=entity.last_login_at,
    )
