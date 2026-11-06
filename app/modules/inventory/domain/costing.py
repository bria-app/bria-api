"""Inventory module domain — weighted average cost (costo promedio ponderado)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def weighted_average_cost(
    on_hand: int, current_avg: Decimal, quantity: int, unit_cost: Decimal
) -> Decimal:
    """New average after receiving `quantity` units at `unit_cost`.

    Negative or zero stock on hand carries no value, so the incoming cost wins.
    """
    on_hand = max(on_hand, 0)
    total_qty = on_hand + quantity
    if total_qty <= 0:
        return Decimal(unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    value = Decimal(on_hand) * Decimal(current_avg) + Decimal(quantity) * Decimal(unit_cost)
    return (value / Decimal(total_qty)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
