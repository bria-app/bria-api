"""Companies module — application output DTOs.

These are the application layer's output contract. Use cases return DTOs (not ORM
models nor raw entities) so the presentation layer has a stable shape to serialize.
Inputs are passed to use cases as explicit typed parameters.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.companies.domain.entities import Company, User


class CompanyDTO(BaseModel):
    id: UUID
    name: str
    tax_id: str
    business_type: str
    address: str
    phone: str
    email: str
    plan: str
    status: str

    @classmethod
    def from_entity(cls, company: Company) -> CompanyDTO:
        assert company.id is not None
        return cls(
            id=company.id,
            name=company.name,
            tax_id=company.tax_id,
            business_type=company.business_type,
            address=company.address,
            phone=company.phone,
            email=company.email.value,
            plan=company.plan.value,
            status=company.status.value,
        )


class UserDTO(BaseModel):
    id: UUID
    company_id: UUID
    email: str | None
    username: str | None
    full_name: str
    role: str
    status: str
    last_login_at: datetime | None

    @classmethod
    def from_entity(cls, user: User) -> UserDTO:
        assert user.id is not None
        return cls(
            id=user.id,
            company_id=user.company_id,
            email=user.email.value if user.email else None,
            username=user.username,
            full_name=user.full_name,
            role=user.role.value,
            status=user.status.value,
            last_login_at=user.last_login_at,
        )
