"""Inventory module — presentation DI providers and enum parsers."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.inventory.domain.enums import MovementType, ReplenishmentStatus
from app.modules.inventory.infrastructure.adapters.costing import (
    SqlInboundCosting,
    SqlStockReader,
)
from app.modules.inventory.infrastructure.persistence.overview import SqlInventoryOverviewQuery
from app.modules.inventory.infrastructure.persistence.repositories import (
    SqlInventoryMovementRepository,
    SqlReplenishmentRepository,
    SqlStockoutEventRepository,
    SqlStockSnapshotRepository,
)
from app.modules.products.infrastructure.persistence.repositories import (
    SqlProductRepository,
)
from app.shared.domain.errors import ValidationError
from app.shared.infrastructure.database import get_db


def get_product_repository(db: Session = Depends(get_db, scope="function")) -> SqlProductRepository:
    return SqlProductRepository(db)


def get_movement_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlInventoryMovementRepository:
    return SqlInventoryMovementRepository(db)


def get_snapshot_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlStockSnapshotRepository:
    return SqlStockSnapshotRepository(db)


def get_replenishment_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlReplenishmentRepository:
    return SqlReplenishmentRepository(db)


def get_stockout_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlStockoutEventRepository:
    return SqlStockoutEventRepository(db)


def get_inbound_costing(db: Session = Depends(get_db, scope="function")) -> SqlInboundCosting:
    return SqlInboundCosting(db)


def get_stock_reader(db: Session = Depends(get_db, scope="function")) -> SqlStockReader:
    return SqlStockReader(db)


def get_overview_query(db: Session = Depends(get_db, scope="function")) -> SqlInventoryOverviewQuery:
    return SqlInventoryOverviewQuery(db)


def parse_movement_type(value: str) -> MovementType:
    try:
        return MovementType(value)
    except ValueError as exc:
        valid = ", ".join(t.value for t in MovementType)
        raise ValidationError(
            message=f"El tipo de movimiento «{value}» no existe. Elige uno de: {valid}."
        ) from exc


def parse_replenishment_status(value: str) -> ReplenishmentStatus:
    try:
        return ReplenishmentStatus(value)
    except ValueError as exc:
        valid = ", ".join(s.value for s in ReplenishmentStatus)
        raise ValidationError(
            message=f"El estado «{value}» no existe. Elige uno de: {valid}."
        ) from exc
