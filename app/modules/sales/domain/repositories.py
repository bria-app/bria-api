"""Sales module domain — repository and collaborator ports."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.modules.sales.domain.entities import (
    CatalogProduct,
    LostSale,
    Sale,
    SalesBatch,
    SalesOrder,
)


class SaleRepository(Protocol):
    """Port for Sale persistence."""

    def get_by_id(self, sale_id: UUID) -> Sale | None: ...
    def list_by_product_and_range(
        self, company_id: UUID, product_id: UUID, start: date, end: date
    ) -> list[Sale]: ...
    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50, origin: str | None = None
    ) -> list[Sale]: ...
    def add(self, sale: Sale) -> Sale: ...
    def add_bulk(self, sales: list[Sale]) -> list[Sale]: ...
    def delete(self, sale_id: UUID) -> bool: ...
    def delete_by_batch(self, company_id: UUID, batch_id: UUID) -> int: ...


class SalesBatchRepository(Protocol):
    """Port for SalesBatch persistence."""

    def get_by_id(self, batch_id: UUID) -> SalesBatch | None: ...
    def list_by_company(self, company_id: UUID) -> list[SalesBatch]: ...
    def add(self, batch: SalesBatch) -> SalesBatch: ...
    def update(self, batch: SalesBatch) -> SalesBatch: ...


class SalesOrderRepository(Protocol):
    """Port for POS tickets (header + product lines)."""

    def next_order_number(self, company_id: UUID) -> int: ...
    def add(self, order: SalesOrder) -> SalesOrder: ...
    def get(self, company_id: UUID, order_id: UUID) -> SalesOrder | None: ...
    def update(self, order: SalesOrder) -> SalesOrder: ...


class LostSaleRepository(Protocol):
    def add(self, lost_sale: LostSale) -> LostSale: ...


class ProductCatalog(Protocol):
    """Read-only access to the product catalog with stock on hand."""

    def get_many(self, company_id: UUID, product_ids: list[UUID]) -> dict[UUID, CatalogProduct]: ...
    def lookup(self, company_id: UUID, code: str) -> CatalogProduct | None: ...
    def search(self, company_id: UUID, query: str, limit: int) -> list[CatalogProduct]: ...


class StockLedger(Protocol):
    """Inventory movements: the source of stock on hand."""

    def on_hand(self, company_id: UUID, product_id: UUID) -> int: ...
    def record(
        self,
        company_id: UUID,
        product_id: UUID,
        *,
        movement_type: str,
        quantity: int,
        unit_cost: Decimal | None,
        reason: str,
        reference_type: str,
        reference_id: UUID,
        occurred_at: datetime,
    ) -> None: ...
    def units_taken_out(self, company_id: UUID, reference_id: UUID) -> dict[UUID, int]:
        """Units per product that the sale `reference_id` actually took out of stock
        (imported history does not move stock, so it has none)."""
        ...


@dataclass(frozen=True)
class IssuedInvoice:
    id: UUID
    document_number: str


class InvoiceIssuer(Protocol):
    """Issues / voids the SUNAT-style comprobante for a ticket (invoicing module)."""

    def issue(self, order: SalesOrder) -> IssuedInvoice: ...
    def void(self, company_id: UUID, invoice_id: UUID) -> None: ...
