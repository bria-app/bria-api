"""Inventory module domain — pure services.

The current stock of a product is *derived* from its movement ledger rather than
stored directly. Inbound adds, outbound subtracts, and adjustment is treated as a
signed positive correction (negative corrections must be modeled as outbound).
"""
from __future__ import annotations

from app.modules.inventory.domain.entities import InventoryMovement
from app.modules.inventory.domain.enums import MovementType


def compute_stock_on_hand(movements: list[InventoryMovement]) -> int:
    total = 0
    for movement in movements:
        if movement.movement_type == MovementType.OUTBOUND:
            total -= movement.quantity.value
        else:  # INBOUND or ADJUSTMENT
            total += movement.quantity.value
    return total
