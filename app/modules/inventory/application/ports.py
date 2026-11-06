"""Inventory module — application ports implemented by infrastructure adapters."""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol
from uuid import UUID


class StockReader(Protocol):
    def on_hand(self, company_id: UUID, product_id: UUID) -> int: ...


class InboundCosting(Protocol):
    def apply(self, company_id: UUID, product_id: UUID, quantity: int, unit_cost: Decimal) -> None:
        """Recompute the weighted-average cost before an inbound movement is stored."""
        ...
