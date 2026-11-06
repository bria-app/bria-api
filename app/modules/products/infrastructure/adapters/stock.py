"""Products module — adapters for the application ports (codes, stock, unit of work)."""
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.inventory.infrastructure.persistence.models import InventoryMovementModel
from app.modules.inventory.infrastructure.persistence.queries import (
    apply_inbound_cost,
    stock_on_hand,
)
from app.modules.products.infrastructure.persistence.codes import next_product_code
from app.modules.products.infrastructure.persistence.models import ProductModel


class SqlProductCodeGenerator:
    def __init__(self, session: Session) -> None:
        self._session = session

    def next_code(self, company_id: UUID) -> str:
        return next_product_code(self._session, company_id)


class SqlProductStockGateway:
    """Writes to the inventory ledger on behalf of product create/import."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def on_hand(self, company_id: UUID, product_id: UUID) -> int:
        return stock_on_hand(self._session, company_id, product_id)

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
        if quantity <= 0:
            return
        cost = unit_cost
        if cost is not None:
            apply_inbound_cost(self._session, company_id, product_id, quantity, cost)
        else:
            product = self._session.get(ProductModel, product_id)
            cost = product.unit_cost if product is not None else None
        self._session.add(
            InventoryMovementModel(
                company_id=company_id,
                product_id=product_id,
                movement_type="inbound",
                quantity=quantity,
                reason=reason,
                occurred_at=datetime.now(timezone.utc),
                unit_cost=cost,
                reference_type=reference_type,
            )
        )
        self._session.flush()

    def remove(
        self,
        company_id: UUID,
        product_id: UUID,
        quantity: int,
        *,
        reason: str,
        reference_type: str,
    ) -> None:
        if quantity <= 0:
            return
        product = self._session.get(ProductModel, product_id)
        self._session.add(
            InventoryMovementModel(
                company_id=company_id,
                product_id=product_id,
                movement_type="outbound",
                quantity=quantity,
                reason=reason,
                occurred_at=datetime.now(timezone.utc),
                unit_cost=product.unit_cost if product is not None else None,
                reference_type=reference_type,
            )
        )
        self._session.flush()


class SqlUnitOfWork:
    def __init__(self, session: Session) -> None:
        self._session = session

    def savepoint(self) -> AbstractContextManager[object]:
        return self._session.begin_nested()
