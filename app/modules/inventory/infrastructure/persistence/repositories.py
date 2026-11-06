"""Inventory module — SQLAlchemy repository implementations."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.inventory.domain.entities import (
    InventoryMovement,
    Replenishment,
    StockoutEvent,
    StockSnapshot,
)
from app.modules.inventory.domain.exceptions import (
    ReplenishmentNotFoundError,
    StockoutEventNotFoundError,
)
from app.modules.inventory.infrastructure.persistence.mappers import (
    movement_to_entity,
    movement_to_model,
    replenishment_to_entity,
    replenishment_to_model,
    snapshot_to_entity,
    snapshot_to_model,
    stockout_to_entity,
    stockout_to_model,
)
from app.modules.inventory.infrastructure.persistence.models import (
    InventoryMovementModel,
    ReplenishmentModel,
    StockoutEventModel,
    StockSnapshotModel,
)


class SqlInventoryMovementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, movement_id: UUID) -> InventoryMovement | None:
        model = self._session.get(InventoryMovementModel, movement_id)
        return movement_to_entity(model) if model else None

    def list_by_product(
        self, product_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[InventoryMovement]:
        rows = self._session.execute(
            select(InventoryMovementModel)
            .where(InventoryMovementModel.product_id == product_id)
            .order_by(InventoryMovementModel.occurred_at)
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return [movement_to_entity(m) for m in rows]

    def list_by_company(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
        reference_type: str | None = None,
    ) -> list[InventoryMovement]:
        """Newest first. reference_type narrows to one origin ("sale", "purchase"...); the id
        breaks ties so paging never repeats or skips movements registered at the same instant."""
        stmt = select(InventoryMovementModel).where(InventoryMovementModel.company_id == company_id)
        if reference_type:
            stmt = stmt.where(InventoryMovementModel.reference_type == reference_type)
        rows = self._session.execute(
            stmt.order_by(InventoryMovementModel.occurred_at.desc(), InventoryMovementModel.id)
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return [movement_to_entity(m) for m in rows]

    def add(self, movement: InventoryMovement) -> InventoryMovement:
        model = movement_to_model(movement)
        self._session.add(model)
        self._session.flush()
        return movement_to_entity(model)

    def add_bulk(self, movements: list[InventoryMovement]) -> list[InventoryMovement]:
        models = [movement_to_model(m) for m in movements]
        self._session.add_all(models)
        self._session.flush()
        return [movement_to_entity(m) for m in models]

    def delete_by_reason(self, company_id: UUID, reason: str) -> int:
        """Remove movements tagged with a specific reason (idempotent auto-seeding)."""
        result = self._session.execute(
            delete(InventoryMovementModel).where(
                InventoryMovementModel.company_id == company_id,
                InventoryMovementModel.reason == reason,
            )
        )
        self._session.flush()
        return int(getattr(result, "rowcount", 0) or 0)


class SqlStockSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_latest_by_product(self, product_id: UUID) -> StockSnapshot | None:
        model = self._session.execute(
            select(StockSnapshotModel)
            .where(StockSnapshotModel.product_id == product_id)
            .order_by(StockSnapshotModel.snapshot_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return snapshot_to_entity(model) if model else None

    def list_by_product(
        self, product_id: UUID, since: datetime | None = None
    ) -> list[StockSnapshot]:
        stmt = select(StockSnapshotModel).where(
            StockSnapshotModel.product_id == product_id
        )
        if since is not None:
            stmt = stmt.where(StockSnapshotModel.snapshot_at >= since)
        rows = self._session.execute(
            stmt.order_by(StockSnapshotModel.snapshot_at.desc())
        ).scalars().all()
        return [snapshot_to_entity(m) for m in rows]

    def add(self, snapshot: StockSnapshot) -> StockSnapshot:
        model = snapshot_to_model(snapshot)
        self._session.add(model)
        self._session.flush()
        return snapshot_to_entity(model)


class SqlReplenishmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, replenishment_id: UUID) -> Replenishment | None:
        model = self._session.get(ReplenishmentModel, replenishment_id)
        return replenishment_to_entity(model) if model else None

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Replenishment]:
        rows = self._session.execute(
            select(ReplenishmentModel)
            .where(ReplenishmentModel.company_id == company_id)
            .order_by(ReplenishmentModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return [replenishment_to_entity(m) for m in rows]

    def add(self, replenishment: Replenishment) -> Replenishment:
        model = replenishment_to_model(replenishment)
        self._session.add(model)
        self._session.flush()
        return replenishment_to_entity(model)

    def update(self, replenishment: Replenishment) -> Replenishment:
        model = self._session.get(ReplenishmentModel, replenishment.id)
        if model is None:
            raise ReplenishmentNotFoundError(
                message="No encontramos esa reposición. Actualiza la página e inténtalo de nuevo."
            )
        model.quantity = replenishment.quantity.value
        model.status = replenishment.status.value
        self._session.flush()
        return replenishment_to_entity(model)


class SqlStockoutEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, event_id: UUID) -> StockoutEvent | None:
        model = self._session.get(StockoutEventModel, event_id)
        return stockout_to_entity(model) if model else None

    def list_open_by_company(self, company_id: UUID) -> list[StockoutEvent]:
        rows = self._session.execute(
            select(StockoutEventModel).where(
                StockoutEventModel.company_id == company_id,
                StockoutEventModel.ended_at.is_(None),
            )
        ).scalars().all()
        return [stockout_to_entity(m) for m in rows]

    def list_by_product(self, product_id: UUID) -> list[StockoutEvent]:
        rows = self._session.execute(
            select(StockoutEventModel)
            .where(StockoutEventModel.product_id == product_id)
            .order_by(StockoutEventModel.started_at.desc())
        ).scalars().all()
        return [stockout_to_entity(m) for m in rows]

    def add(self, event: StockoutEvent) -> StockoutEvent:
        model = stockout_to_model(event)
        self._session.add(model)
        self._session.flush()
        return stockout_to_entity(model)

    def update(self, event: StockoutEvent) -> StockoutEvent:
        model = self._session.get(StockoutEventModel, event.id)
        if model is None:
            raise StockoutEventNotFoundError(
                message="No encontramos ese quiebre de stock. Actualiza la página e inténtalo de nuevo."
            )
        model.ended_at = event.ended_at
        self._session.flush()
        return stockout_to_entity(model)
