"""Inventory module — who may see costs and stock value at cost.

A seller (cashier) may look stock up — units, prices, status — but not what each product
cost the shop, the stock value at cost or the margin. The queries always compute
everything; these helpers blank the cost fields (None) for a role that may not see them.
"""
from __future__ import annotations

from app.modules.inventory.application.dtos import (
    InventoryOverviewDTO,
    InventoryTotalsDTO,
    InventoryValuationDTO,
    MovementDTO,
)

COST_BLIND_ROLES = frozenset({"seller"})


def can_see_costs(role: str) -> bool:
    return role not in COST_BLIND_ROLES


def _totals(totals: InventoryTotalsDTO) -> InventoryTotalsDTO:
    return totals.model_copy(update={"inventory_value_cost": None, "potential_margin": None})


def overview_for(role: str, overview: InventoryOverviewDTO) -> InventoryOverviewDTO:
    if can_see_costs(role):
        return overview
    return overview.model_copy(
        update={
            "items": [
                item.model_copy(update={"unit_cost": None, "last_cost": None, "stock_value": None})
                for item in overview.items
            ],
            "totals": _totals(overview.totals),
        }
    )


def valuation_for(role: str, valuation: InventoryValuationDTO) -> InventoryValuationDTO:
    if can_see_costs(role):
        return valuation
    blank = {"value_cost": None, "share_pct": None}
    return valuation.model_copy(
        update={
            "totals": _totals(valuation.totals),
            "by_category": [g.model_copy(update=blank) for g in valuation.by_category],
            "by_brand": [g.model_copy(update=blank) for g in valuation.by_brand],
        }
    )


def movement_for(role: str, movement: MovementDTO) -> MovementDTO:
    if can_see_costs(role):
        return movement
    return movement.model_copy(update={"unit_cost": None})


def movements_for(role: str, movements: list[MovementDTO]) -> list[MovementDTO]:
    if can_see_costs(role):
        return movements
    return [movement_for(role, m) for m in movements]
