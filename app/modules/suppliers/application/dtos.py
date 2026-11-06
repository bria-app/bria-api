"""Suppliers module — application output DTOs."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.modules.suppliers.domain.entities import Supplier


class SupplierDTO(BaseModel):
    id: UUID
    company_id: UUID
    ruc: str
    business_name: str
    contact_name: str
    phone: str
    email: str
    address: str
    is_active: bool
    custom_attributes: dict[str, Any] = {}
    # Purchase figures (filled on list; zero/None elsewhere).
    total_purchased: Decimal = Decimal("0")
    purchase_lines: int = 0
    last_purchase_date: date | None = None

    @classmethod
    def from_entity(cls, supplier: Supplier, stats: dict[str, Any] | None = None) -> SupplierDTO:
        assert supplier.id is not None
        stats = stats or {}
        return cls(
            id=supplier.id,
            company_id=supplier.company_id,
            ruc=supplier.ruc,
            business_name=supplier.business_name,
            contact_name=supplier.contact_name,
            phone=supplier.phone,
            email=supplier.email,
            address=supplier.address,
            is_active=supplier.is_active,
            custom_attributes=dict(supplier.custom_attributes or {}),
            total_purchased=stats.get("total_purchased", Decimal("0")),
            purchase_lines=stats.get("purchase_lines", 0),
            last_purchase_date=stats.get("last_purchase_date"),
        )


class SuppliedProductDTO(BaseModel):
    product_id: UUID
    sku: str
    name: str
    total_quantity: int
    total_amount: Decimal
    avg_unit_cost: Decimal
    last_cost: Decimal | None
    last_purchase_date: date | None


class SupplierPurchaseLineDTO(BaseModel):
    id: UUID
    document_id: str | None
    document_number: str
    purchase_date: date
    product_id: UUID
    product_name: str
    sku: str
    quantity: int
    unit_cost: Decimal
    total_amount: Decimal


class SupplierSummaryDTO(BaseModel):
    supplier: SupplierDTO
    total_purchased: Decimal
    purchases_count: int
    documents_count: int
    last_purchase_date: date | None
    products_count: int
    products: list[SuppliedProductDTO]
    recent_lines: list[SupplierPurchaseLineDTO]


class ImportErrorDTO(BaseModel):
    row: int
    message: str


class SupplierImportResultDTO(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[ImportErrorDTO]
