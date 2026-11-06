"""Purchases module — presentation request schemas."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CreatePurchaseRequest(BaseModel):
    supplier_id: UUID
    product_id: UUID
    purchase_date: date
    quantity: int
    unit_cost: Decimal
    currency: str = "PEN"
    document_number: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=500)
    costs_include_igv: bool = False


class NewProductPayload(BaseModel):
    name: str
    sku: str | None = Field(default=None, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    unit_price: Decimal | None = None
    category_id: UUID | None = None
    custom_attributes: dict[str, Any] | None = None


class PurchaseBatchItem(BaseModel):
    product_id: UUID | None = None
    new_product: NewProductPayload | None = None
    quantity: Decimal
    unit_cost: Decimal


class PurchaseBatchRequest(BaseModel):
    supplier_id: UUID
    purchase_date: date
    document_number: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=500)
    # True when the typed unit costs already include 18% IGV; stored net (÷ 1.18).
    costs_include_igv: bool = False
    items: list[PurchaseBatchItem] = Field(default_factory=list, max_length=500)


class PurchaseImportRow(BaseModel):
    row: int | None = None
    code: str | None = None
    barcode: str | None = None
    name: str | None = None
    quantity: Any = None
    unit_cost: Any = None
    unit_price: Any = None
    purchase_date: str | None = None
    document_number: str | None = Field(default=None, max_length=40)
    custom_attributes: dict[str, Any] | None = None


class PurchaseImportRequest(BaseModel):
    supplier_id: UUID
    purchase_date: date
    document_number: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=500)
    create_missing_products: bool = True
    costs_include_igv: bool = False
    rows: list[PurchaseImportRow] = Field(default_factory=list, max_length=10000)
