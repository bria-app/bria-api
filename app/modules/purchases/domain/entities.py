"""Purchases module domain — entities.

A Purchase row is ONE LINE of a supplier document (factura / boleta / guía): stock of a
single product bought at a negotiated unit_cost. Lines registered together share an
`import_batch_id` (the document id); legacy lines without one are grouped by
(supplier_id, document_number, purchase_date).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.shared.domain.value_objects import Money, Quantity


@dataclass
class Purchase:
    company_id: UUID
    supplier_id: UUID
    product_id: UUID
    purchase_date: date
    quantity: Quantity
    unit_cost: Money
    total_amount: Money
    document_number: str = ""
    notes: str = ""
    import_batch_id: UUID | None = None
    id: UUID | None = None


@dataclass(frozen=True)
class ProductRef:
    """Minimal view of a catalog product as the purchases module needs it."""

    id: UUID
    sku: str
    name: str


@dataclass(frozen=True)
class StockReceipt:
    """Effect of receiving stock: on-hand and weighted-average cost, before and after."""

    product_id: UUID
    quantity: int
    previous_stock: int
    new_stock: int
    previous_avg_cost: Decimal
    new_avg_cost: Decimal
