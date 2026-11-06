"""Purchases module domain — repository ports."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.modules.purchases.domain.entities import ProductRef, Purchase, StockReceipt


class PurchaseRepository(Protocol):
    """Port for Purchase persistence and document-level reads."""

    def get_by_id(self, purchase_id: UUID) -> Purchase | None: ...
    def add(self, purchase: Purchase) -> Purchase: ...
    def list_lines(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...
    def list_documents(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        q: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]: ...
    def get_document(self, company_id: UUID, document_id: str) -> dict[str, Any] | None: ...


class InboundStockGateway(Protocol):
    """Port to the catalog + inventory side effects of receiving a purchase."""

    def savepoint(self) -> Any: ...
    def supplier_exists(self, company_id: UUID, supplier_id: UUID) -> bool: ...
    def get_product(self, company_id: UUID, product_id: UUID) -> ProductRef | None: ...
    def find_product(
        self, company_id: UUID, *, code: str | None, barcode: str | None, name: str | None
    ) -> tuple[ProductRef, str] | None: ...
    def sku_taken(self, company_id: UUID, sku: str) -> bool: ...
    def create_product(
        self,
        company_id: UUID,
        *,
        name: str,
        sku: str | None,
        barcode: str | None,
        unit_price: Decimal | None,
        category_id: UUID | None,
        custom_attributes: dict[str, Any] | None,
    ) -> ProductRef: ...
    def update_product(
        self,
        company_id: UUID,
        product_id: UUID,
        *,
        unit_price: Decimal | None = None,
        custom_attributes: dict[str, Any] | None = None,
    ) -> None: ...
    def receive(
        self,
        company_id: UUID,
        product_id: UUID,
        *,
        quantity: int,
        unit_cost: Decimal,
        reason: str,
        reference_id: UUID,
        occurred_at: datetime,
    ) -> StockReceipt: ...
    def catalog(self, company_id: UUID) -> list[dict[str, Any]]: ...
