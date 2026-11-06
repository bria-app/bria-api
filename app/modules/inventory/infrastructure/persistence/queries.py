"""Inventory module — shared read helpers + inbound costing used across modules.

Stock on hand is derived from movements: inbound and adjustment add, outbound
subtracts (same rule as domain.services.compute_stock_on_hand).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.modules.inventory.domain.costing import weighted_average_cost
from app.modules.inventory.infrastructure.persistence.models import InventoryMovementModel
from app.modules.products.infrastructure.persistence.models import ProductModel

_SIGNED_QTY = case(
    (InventoryMovementModel.movement_type == "outbound", -InventoryMovementModel.quantity),
    else_=InventoryMovementModel.quantity,
)


def stock_on_hand(session: Session, company_id: UUID, product_id: UUID) -> int:
    return int(
        session.execute(
            select(func.coalesce(func.sum(_SIGNED_QTY), 0)).where(
                InventoryMovementModel.company_id == company_id,
                InventoryMovementModel.product_id == product_id,
            )
        ).scalar_one()
    )


def stock_on_hand_map(session: Session, company_id: UUID) -> dict[UUID, int]:
    rows = session.execute(
        select(InventoryMovementModel.product_id, func.sum(_SIGNED_QTY))
        .where(InventoryMovementModel.company_id == company_id)
        .group_by(InventoryMovementModel.product_id)
    ).all()
    return {pid: int(total or 0) for pid, total in rows}


def apply_inbound_cost(
    session: Session, company_id: UUID, product_id: UUID, quantity: int, unit_cost: Decimal
) -> None:
    """Update the product's weighted average cost and last cost for a receipt.

    Call it BEFORE inserting the inbound movement, so on-hand reflects the stock
    that existed prior to this receipt.
    """
    product = session.get(ProductModel, product_id)
    if product is None or product.company_id != company_id:
        return
    on_hand = stock_on_hand(session, company_id, product_id)
    product.unit_cost = weighted_average_cost(on_hand, product.unit_cost, quantity, Decimal(unit_cost))
    product.last_cost = Decimal(unit_cost)
    session.flush()
