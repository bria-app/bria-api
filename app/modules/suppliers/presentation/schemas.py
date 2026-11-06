"""Suppliers module — presentation request schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSupplierRequest(BaseModel):
    ruc: str
    business_name: str
    contact_name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    custom_attributes: dict[str, Any] = Field(default_factory=dict)


class UpdateSupplierRequest(BaseModel):
    business_name: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_active: bool | None = None
    custom_attributes: dict[str, Any] | None = None


class ImportSupplierRow(BaseModel):
    row: int | None = None
    ruc: str = ""
    business_name: str = ""
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    custom_attributes: dict[str, Any] | None = None


class ImportSuppliersRequest(BaseModel):
    rows: list[ImportSupplierRow] = Field(default_factory=list, max_length=5000)
