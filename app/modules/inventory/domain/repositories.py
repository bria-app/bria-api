"""Inventory module domain — repository ports."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.inventory.domain.entities import (
    InventoryMovement,
    Replenishment,
    StockoutEvent,
    StockSnapshot,
)


class InventoryMovementRepository(Protocol):
    """Port for InventoryMovement persistence."""

    def get_by_id(self, movement_id: UUID) -> InventoryMovement | None: ...
    def list_by_product(
        self, product_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[InventoryMovement]: ...
    def list_by_company(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
        reference_type: str | None = None,
    ) -> list[InventoryMovement]: ...
    def add(self, movement: InventoryMovement) -> InventoryMovement: ...
    def add_bulk(self, movements: list[InventoryMovement]) -> list[InventoryMovement]: ...
    def delete_by_reason(self, company_id: UUID, reason: str) -> int: ...


class StockSnapshotRepository(Protocol):
    """Port for StockSnapshot persistence."""

    def get_latest_by_product(self, product_id: UUID) -> StockSnapshot | None: ...
    def list_by_product(
        self, product_id: UUID, since: datetime | None = None
    ) -> list[StockSnapshot]: ...
    def add(self, snapshot: StockSnapshot) -> StockSnapshot: ...


class ReplenishmentRepository(Protocol):
    """Port for Replenishment persistence."""

    def get_by_id(self, replenishment_id: UUID) -> Replenishment | None: ...
    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Replenishment]: ...
    def add(self, replenishment: Replenishment) -> Replenishment: ...
    def update(self, replenishment: Replenishment) -> Replenishment: ...


class StockoutEventRepository(Protocol):
    """Port for StockoutEvent persistence."""

    def get_by_id(self, event_id: UUID) -> StockoutEvent | None: ...
    def list_open_by_company(self, company_id: UUID) -> list[StockoutEvent]: ...
    def list_by_product(self, product_id: UUID) -> list[StockoutEvent]: ...
    def add(self, event: StockoutEvent) -> StockoutEvent: ...
    def update(self, event: StockoutEvent) -> StockoutEvent: ...
