"""Auth module — presentation request schemas."""
from __future__ import annotations

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    company_name: str
    tax_id: str
    business_type: str = ""


class LoginRequest(BaseModel):
    """`email` accepts an email or a username (backward compatible); `identifier` is an alias."""

    email: str | None = None
    identifier: str | None = None
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
