"""Inventory module — SQL adapters for stock reading and inbound costing."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.inventory.infrastructure.persistence.queries import (
    apply_inbound_cost,
    stock_on_hand,
)


class SqlStockReader:
    def __init__(self, session: Session) -> None:
        self._session = session

    def on_hand(self, company_id: UUID, product_id: UUID) -> int:
        return stock_on_hand(self._session, company_id, product_id)


class SqlInboundCosting:
    def __init__(self, session: Session) -> None:
        self._session = session

    def apply(self, company_id: UUID, product_id: UUID, quantity: int, unit_cost: Decimal) -> None:
        apply_inbound_cost(self._session, company_id, product_id, quantity, unit_cost)
