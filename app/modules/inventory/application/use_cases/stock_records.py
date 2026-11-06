"""Inventory module — snapshot, replenishment and stockout use cases."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.modules.inventory.application.dtos import (
    ReplenishmentDTO,
    SnapshotDTO,
    StockoutDTO,
)
from app.modules.inventory.domain.entities import (
    Replenishment,
    StockoutEvent,
    StockSnapshot,
)
from app.modules.inventory.domain.enums import ReplenishmentStatus
from app.modules.inventory.domain.exceptions import (
    ReplenishmentNotFoundError,
    StockoutEventNotFoundError,
)
from app.modules.inventory.domain.repositories import (
    ReplenishmentRepository,
    StockoutEventRepository,
    StockSnapshotRepository,
)
from app.shared.domain.value_objects import Quantity


# --- Snapshots ---------------------------------------------------------------
class CreateSnapshot:
    def __init__(self, snapshots: StockSnapshotRepository) -> None:
        self._snapshots = snapshots

    def execute(
        self,
        company_id: UUID,
        *,
        product_id: UUID,
        quantity_on_hand: int,
        snapshot_at: datetime | None = None,
    ) -> SnapshotDTO:
        snapshot = StockSnapshot(
            company_id=company_id,
            product_id=product_id,
            quantity_on_hand=Quantity(quantity_on_hand),
            snapshot_at=snapshot_at or datetime.now(timezone.utc),
        )
        return SnapshotDTO.from_entity(self._snapshots.add(snapshot))


class ListProductSnapshots:
    def __init__(self, snapshots: StockSnapshotRepository) -> None:
        self._snapshots = snapshots

    def execute(self, company_id: UUID, product_id: UUID) -> list[SnapshotDTO]:
        return [
            SnapshotDTO.from_entity(s)
            for s in self._snapshots.list_by_product(product_id)
            if s.company_id == company_id
        ]


# --- Replenishments ----------------------------------------------------------
class CreateReplenishment:
    def __init__(self, replenishments: ReplenishmentRepository) -> None:
        self._replenishments = replenishments

    def execute(
        self, company_id: UUID, *, product_id: UUID, quantity: int
    ) -> ReplenishmentDTO:
        replenishment = Replenishment(
            company_id=company_id,
            product_id=product_id,
            quantity=Quantity(quantity),
        )
        return ReplenishmentDTO.from_entity(
            self._replenishments.add(replenishment)
        )


class ListReplenishments:
    def __init__(self, replenishments: ReplenishmentRepository) -> None:
        self._replenishments = replenishments

    def execute(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[ReplenishmentDTO]:
        return [
            ReplenishmentDTO.from_entity(r)
            for r in self._replenishments.list_by_company(company_id, offset, limit)
        ]


class UpdateReplenishmentStatus:
    def __init__(self, replenishments: ReplenishmentRepository) -> None:
        self._replenishments = replenishments

    def execute(
        self, company_id: UUID, replenishment_id: UUID, *, status: ReplenishmentStatus
    ) -> ReplenishmentDTO:
        replenishment = self._replenishments.get_by_id(replenishment_id)
        if replenishment is None or replenishment.company_id != company_id:
            raise ReplenishmentNotFoundError(
                message="No encontramos esa reposición. Actualiza la página e inténtalo de nuevo."
            )
        replenishment.status = status
        return ReplenishmentDTO.from_entity(
            self._replenishments.update(replenishment)
        )


# --- Stockout events ---------------------------------------------------------
class CreateStockout:
    def __init__(self, stockouts: StockoutEventRepository) -> None:
        self._stockouts = stockouts

    def execute(
        self,
        company_id: UUID,
        *,
        product_id: UUID,
        started_at: datetime | None = None,
    ) -> StockoutDTO:
        event = StockoutEvent(
            company_id=company_id,
            product_id=product_id,
            started_at=started_at or datetime.now(timezone.utc),
        )
        return StockoutDTO.from_entity(self._stockouts.add(event))


class ListOpenStockouts:
    def __init__(self, stockouts: StockoutEventRepository) -> None:
        self._stockouts = stockouts

    def execute(self, company_id: UUID) -> list[StockoutDTO]:
        return [
            StockoutDTO.from_entity(e)
            for e in self._stockouts.list_open_by_company(company_id)
        ]


class CloseStockout:
    def __init__(self, stockouts: StockoutEventRepository) -> None:
        self._stockouts = stockouts

    def execute(
        self, company_id: UUID, stockout_id: UUID, *, ended_at: datetime | None = None
    ) -> StockoutDTO:
        event = self._stockouts.get_by_id(stockout_id)
        if event is None or event.company_id != company_id:
            raise StockoutEventNotFoundError(
                message="No encontramos ese quiebre de stock. Actualiza la página e inténtalo de nuevo."
            )
        event.close(ended_at or datetime.now(timezone.utc))
        return StockoutDTO.from_entity(self._stockouts.update(event))
