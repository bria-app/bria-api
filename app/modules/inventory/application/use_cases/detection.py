"""Inventory module — automatic stockout detection.

For each active product, derives current stock from the movement ledger and opens a
StockoutEvent when stock has run out and there is no open event yet. Cross-module: reads
the product catalogue.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.modules.inventory.application.dtos import StockoutDTO
from app.modules.inventory.domain.entities import StockoutEvent
from app.modules.inventory.domain.repositories import (
    InventoryMovementRepository,
    StockoutEventRepository,
)
from app.modules.inventory.domain.services import compute_stock_on_hand
from app.modules.products.domain.repositories import ProductRepository

_MOVE_PAGE = 200


class DetectStockouts:
    def __init__(
        self,
        *,
        products: ProductRepository,
        movements: InventoryMovementRepository,
        stockouts: StockoutEventRepository,
    ) -> None:
        self._products = products
        self._movements = movements
        self._stockouts = stockouts

    def _current_stock(self, product_id: UUID) -> int:
        collected = []
        offset = 0
        while True:
            page = self._movements.list_by_product(product_id, offset, _MOVE_PAGE)
            collected.extend(page)
            if len(page) < _MOVE_PAGE:
                break
            offset += _MOVE_PAGE
        return compute_stock_on_hand(collected)

    def execute(self, company_id: UUID) -> list[StockoutDTO]:
        open_products = {
            e.product_id for e in self._stockouts.list_open_by_company(company_id)
        }
        now = datetime.now(timezone.utc)

        opened: list[StockoutDTO] = []
        for product in self._products.list_active(company_id):
            if product.id is None or product.id in open_products:
                continue
            if self._current_stock(product.id) <= 0:
                event = StockoutEvent(
                    company_id=company_id,
                    product_id=product.id,
                    started_at=now,
                )
                opened.append(StockoutDTO.from_entity(self._stockouts.add(event)))
        return opened
