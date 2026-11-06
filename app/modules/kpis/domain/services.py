"""KPIs module domain — pure KPI formulas.

These are the analytical core of the DSS. Each function consumes a product's current
stock, its forecasted daily demand, and its inventory parameters, and returns a KPI
value. No I/O, no frameworks: the formulas are deterministic and unit-testable.

KPIs:
- coverage_days: how many days the current stock lasts at the forecasted demand rate.
- stockout_risk (0-100): shortfall over the lead time plus a two-week margin
  (demand + safety vs stock). No recorded lead time -> 7 days (see recommendations).
- turnover: forecasted demand over the horizon divided by current stock.
- overstock_risk (0-100): share of the stock beyond what ~4 months of sales need
  (same line the action plan uses for "no compres por ahora").
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.kpis.domain.enums import KpiType
from app.modules.recommendations.domain.services import SAFETY_MARGIN_DAYS, effective_lead_time

_COVERAGE_CAP = Decimal("9999")  # sentinel for "effectively infinite" coverage
_OVERSTOCK_DAYS = 120  # more than ~4 months of sales on hand is money standing still


def _clamp_pct(value: Decimal) -> Decimal:
    """Clamp a ratio (0..1) into a 0..100 percentage, rounded to 2 decimals."""
    pct = value * Decimal("100")
    pct = max(Decimal("0"), min(Decimal("100"), pct))
    return pct.quantize(Decimal("0.01"))


@dataclass(frozen=True)
class ProductKpiInputs:
    current_stock: int
    daily_demand: list[Decimal]  # predicted demand per day, in horizon order
    lead_time_days: int
    safety_stock: int = 0

    @property
    def total_demand(self) -> Decimal:
        return sum(self.daily_demand, Decimal("0"))

    @property
    def lead(self) -> int:
        return effective_lead_time(self.lead_time_days)

    def demand_over(self, days: int) -> Decimal:
        """Forecast demand over ``days``, extending the horizon at its average daily rate."""
        if days <= 0 or not self.daily_demand:
            return Decimal("0")
        window = sum(self.daily_demand[:days], Decimal("0"))
        extra = days - len(self.daily_demand)
        if extra > 0:
            window += self.total_demand / Decimal(len(self.daily_demand)) * Decimal(extra)
        return window

    @property
    def demand_over_lead_time(self) -> Decimal:
        return self.demand_over(self.lead)


def coverage_days(inp: ProductKpiInputs) -> Decimal:
    total = inp.total_demand
    horizon = len(inp.daily_demand)
    if total <= 0 or horizon == 0:
        return _COVERAGE_CAP if inp.current_stock > 0 else Decimal("0")
    avg_daily = total / Decimal(horizon)
    days = Decimal(inp.current_stock) / avg_daily
    return min(_COVERAGE_CAP, days.quantize(Decimal("0.01")))


def stockout_risk(inp: ProductKpiInputs) -> Decimal:
    needed = inp.demand_over(inp.lead + SAFETY_MARGIN_DAYS) + Decimal(inp.safety_stock)
    if needed <= 0:
        return Decimal("0")
    shortfall = needed - Decimal(inp.current_stock)
    return _clamp_pct(shortfall / needed)


def turnover(inp: ProductKpiInputs) -> Decimal:
    if inp.current_stock <= 0:
        return Decimal("0")
    return (inp.total_demand / Decimal(inp.current_stock)).quantize(Decimal("0.0001"))


def overstock_risk(inp: ProductKpiInputs) -> Decimal:
    target = inp.demand_over(_OVERSTOCK_DAYS) + Decimal(inp.safety_stock)
    if inp.current_stock <= 0:
        return Decimal("0")
    excess = Decimal(inp.current_stock) - target
    if excess <= 0:
        return Decimal("0")
    return _clamp_pct(excess / Decimal(inp.current_stock))


def compute_all(inp: ProductKpiInputs) -> dict[KpiType, Decimal]:
    return {
        KpiType.COVERAGE_DAYS: coverage_days(inp),
        KpiType.STOCKOUT_RISK: stockout_risk(inp),
        KpiType.TURNOVER: turnover(inp),
        KpiType.OVERSTOCK_RISK: overstock_risk(inp),
    }
