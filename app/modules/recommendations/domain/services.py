"""Recommendations module domain — pure replenishment logic.

Given current stock, forecasted daily demand and inventory parameters, decides whether
to reorder and how much, using a classic order-up-to policy:

    reorder is triggered when stock <= reorder_point OR stock < demand(lead time)+safety
    target level (order-up-to) = demand(lead time + review period) + safety_stock
    suggested quantity = ceil(target - current stock)

Priority reflects urgency (how exposed the stock is over the lead time).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from app.modules.recommendations.domain.enums import RecommendationPriority


#: Supplier lead time assumed when the product has none recorded (0). Imported catalogs
#: rarely carry it, and 0 would mean "arrives instantly" -> never reorder in time.
DEFAULT_LEAD_TIME_DAYS = 7


#: One rule across the ERP (inventory status, "Mis números", "Qué comprar", the forecast's
#: action plan): buy when the stock won't last the supplier's wait plus two weeks.
SAFETY_MARGIN_DAYS = 14


def effective_lead_time(days: int | None) -> int:
    return days if days and days > 0 else DEFAULT_LEAD_TIME_DAYS


@dataclass(frozen=True)
class ReorderInputs:
    current_stock: int
    daily_demand: list[Decimal]  # predicted demand per day, horizon order
    lead_time_days: int
    safety_stock: int = 0
    reorder_point: int = 0
    review_days: int = 30  # MYPEs restock about monthly: cover lead time + a month


@dataclass(frozen=True)
class ReorderSuggestion:
    quantity: int
    priority: RecommendationPriority
    reason: str


def _window_sum(values: list[Decimal], days: int) -> Decimal:
    return sum(values[:days], Decimal("0")) if days > 0 else Decimal("0")


def suggest_reorder(inp: ReorderInputs) -> ReorderSuggestion | None:
    lead = effective_lead_time(inp.lead_time_days)
    demand_lead = _window_sum(inp.daily_demand, lead)
    demand_window = _window_sum(inp.daily_demand, lead + inp.review_days)
    order_up_to = demand_window + Decimal(inp.safety_stock)

    exposure = _window_sum(inp.daily_demand, lead + SAFETY_MARGIN_DAYS) + Decimal(inp.safety_stock)
    triggered = inp.current_stock <= inp.reorder_point or (
        Decimal(inp.current_stock) < exposure
    )
    if not triggered:
        return None

    raw_qty = order_up_to - Decimal(inp.current_stock)
    if raw_qty <= 0:
        return None
    quantity = int(raw_qty.to_integral_value(rounding=ROUND_CEILING))

    # Same urgency the forecast's action plan shows: below safety or not enough to wait
    # for the supplier -> buy now; below what the wait + safety needs -> this week; only
    # the manual reorder point fired -> it can wait for the next order.
    if inp.current_stock <= inp.safety_stock or Decimal(inp.current_stock) < demand_lead:
        priority = RecommendationPriority.HIGH
    elif Decimal(inp.current_stock) < exposure:
        priority = RecommendationPriority.MEDIUM
    else:
        priority = RecommendationPriority.LOW

    reason = (
        f"Stock actual {inp.current_stock}; demanda estimada en lead time "
        f"({lead}d) {demand_lead.quantize(Decimal('0.1'))}. Reponer "
        f"{quantity} unidades para alcanzar el nivel objetivo "
        f"{order_up_to.quantize(Decimal('0.1'))}."
    )
    return ReorderSuggestion(quantity=quantity, priority=priority, reason=reason)
