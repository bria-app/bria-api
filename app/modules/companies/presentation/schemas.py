"""Companies module — presentation request schemas.

Responses reuse the application DTOs (CompanyDTO, UserDTO) as response models.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class UpdateCompanyRequest(BaseModel):
    name: str | None = None
    business_type: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None


class InviteUserRequest(BaseModel):
    email: str
    full_name: str
    role: str = "viewer"
    temporary_password: str


class UpdateUserRoleRequest(BaseModel):
    role: str


class CreateCompanyUserRequest(BaseModel):
    full_name: str
    username: str
    password: str
    role: Literal["seller", "admin"] = "seller"


class UpdateCompanyUserRequest(BaseModel):
    full_name: str | None = None
    password: str | None = None
    status: Literal["active", "disabled"] | None = None
