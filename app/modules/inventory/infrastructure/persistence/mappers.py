"""Inventory module — mappers between ORM models and domain entities."""
from __future__ import annotations

from app.modules.inventory.domain.entities import (
    InventoryMovement,
    Replenishment,
    StockoutEvent,
    StockSnapshot,
)
from app.modules.inventory.domain.enums import MovementType, ReplenishmentStatus
from app.modules.inventory.infrastructure.persistence.models import (
    InventoryMovementModel,
    ReplenishmentModel,
    StockoutEventModel,
    StockSnapshotModel,
)
from app.shared.domain.value_objects import Quantity


def movement_to_entity(model: InventoryMovementModel) -> InventoryMovement:
    return InventoryMovement(
        id=model.id,
        company_id=model.company_id,
        product_id=model.product_id,
        movement_type=MovementType(model.movement_type),
        quantity=Quantity(model.quantity),
        reason=model.reason,
        occurred_at=model.occurred_at,
        unit_cost=model.unit_cost,
        reference_type=model.reference_type,
        reference_id=model.reference_id,
    )


def movement_to_model(entity: InventoryMovement) -> InventoryMovementModel:
    return InventoryMovementModel(
        id=entity.id,
        company_id=entity.company_id,
        product_id=entity.product_id,
        movement_type=entity.movement_type.value,
        quantity=entity.quantity.value,
        reason=entity.reason,
        occurred_at=entity.occurred_at,
        unit_cost=entity.unit_cost,
        reference_type=entity.reference_type,
        reference_id=entity.reference_id,
    )


def snapshot_to_entity(model: StockSnapshotModel) -> StockSnapshot:
    return StockSnapshot(
        id=model.id,
        company_id=model.company_id,
        product_id=model.product_id,
        quantity_on_hand=Quantity(model.quantity_on_hand),
        snapshot_at=model.snapshot_at,
    )


def snapshot_to_model(entity: StockSnapshot) -> StockSnapshotModel:
    return StockSnapshotModel(
        id=entity.id,
        company_id=entity.company_id,
        product_id=entity.product_id,
        quantity_on_hand=entity.quantity_on_hand.value,
        snapshot_at=entity.snapshot_at,
    )


def replenishment_to_entity(model: ReplenishmentModel) -> Replenishment:
    return Replenishment(
        id=model.id,
        company_id=model.company_id,
        product_id=model.product_id,
        quantity=Quantity(model.quantity),
        status=ReplenishmentStatus(model.status),
    )


def replenishment_to_model(entity: Replenishment) -> ReplenishmentModel:
    return ReplenishmentModel(
        id=entity.id,
        company_id=entity.company_id,
        product_id=entity.product_id,
        quantity=entity.quantity.value,
        status=entity.status.value,
    )


def stockout_to_entity(model: StockoutEventModel) -> StockoutEvent:
    return StockoutEvent(
        id=model.id,
        company_id=model.company_id,
        product_id=model.product_id,
        started_at=model.started_at,
        ended_at=model.ended_at,
    )


def stockout_to_model(entity: StockoutEvent) -> StockoutEventModel:
    return StockoutEventModel(
        id=entity.id,
        company_id=entity.company_id,
        product_id=entity.product_id,
        started_at=entity.started_at,
        ended_at=entity.ended_at,
    )
