"""Products module — application ports implemented by infrastructure adapters.

Creating or importing a product touches other concerns: the company's code correlativo
(P-000001...) and the inventory ledger (initial stock valued at cost). The use cases
depend on these small ports instead of on SQLAlchemy or on the inventory module.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID


class ProductCodeGenerator(Protocol):
    def next_code(self, company_id: UUID) -> str: ...


class ProductStockGateway(Protocol):
    def on_hand(self, company_id: UUID, product_id: UUID) -> int: ...

    def receive(
        self,
        company_id: UUID,
        product_id: UUID,
        quantity: int,
        unit_cost: Decimal | None,
        *,
        reason: str,
        reference_type: str,
    ) -> None:
        """Inbound movement; updates weighted-average cost when unit_cost is given."""
        ...

    def remove(
        self,
        company_id: UUID,
        product_id: UUID,
        quantity: int,
        *,
        reason: str,
        reference_type: str,
    ) -> None:
        """Outbound correction (negative adjustment)."""
        ...


class UnitOfWork(Protocol):
    def savepoint(self) -> AbstractContextManager[object]:
        """A nested transaction: rolled back on exception, kept otherwise."""
        ...


class ProductHistory(Protocol):
    def has_history(self, company_id: UUID, product_id: UUID) -> bool:
        """True when sales, purchases, stock movements, lost sales, recommendations or
        forecast results reference the product (deleting it would orphan them)."""
        ...


class CustomAttributeCaster(Protocol):
    def cast(
        self,
        company_id: UUID,
        attributes: dict[str, Any],
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Typed values for the company's own product fields (number, date, Sí/No...),
        checked against each column's validation rules (max length, min/max...).

        Unknown keys come back unchanged, and so do values equal to the ones in
        previous (the product's stored values). Raises a DomainError with a short
        message naming the column when a value does not fit."""
        ...


class ProductAlertSource(Protocol):
    def alerts(
        self, company_id: UUID, products: list[tuple[UUID | None, dict[str, Any]]]
    ) -> list[list[dict[str, str]]]:
        """For each (category_id, custom_attributes), the alerts the company's own
        columns raise: [{key, column, label, tone}] (empty list when none)."""
        ...
