"""Sales module — who may see costs and margins.

A seller (cashier) runs the till: prices and units yes, what the product cost the shop
and the margin no. The read models always compute everything; these helpers blank the
cost fields (None) before the answer leaves for a role that may not see them.
"""
from __future__ import annotations

from app.modules.sales.application.dtos import (
    SaleDTO,
    SalesOrderDTO,
    SalesOrderPageDTO,
    SalesSummaryDTO,
)

COST_BLIND_ROLES = frozenset({"seller"})


def can_see_costs(role: str) -> bool:
    return role not in COST_BLIND_ROLES


def order_for(role: str, order: SalesOrderDTO) -> SalesOrderDTO:
    if can_see_costs(role):
        return order
    return order.model_copy(
        update={
            "cost_total": None,
            "gross_margin": None,
            "lines": [line.model_copy(update={"unit_cost": None}) for line in order.lines],
        }
    )


def order_page_for(role: str, page: SalesOrderPageDTO) -> SalesOrderPageDTO:
    if can_see_costs(role):
        return page
    return page.model_copy(
        update={"items": [row.model_copy(update={"cost_total": None, "margin": None}) for row in page.items]}
    )


def summary_for(role: str, summary: SalesSummaryDTO) -> SalesSummaryDTO:
    if can_see_costs(role):
        return summary
    return summary.model_copy(update={"cost_total": None, "gross_margin": None, "margin_pct": None})


def sales_for(role: str, sales: list[SaleDTO]) -> list[SaleDTO]:
    if can_see_costs(role):
        return sales
    return [s.model_copy(update={"unit_cost": None}) for s in sales]
