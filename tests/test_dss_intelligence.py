"""Bloque 5 — unit tests for the pure DSS formulas (KPIs + reorder policy)."""
from __future__ import annotations

from decimal import Decimal

from app.modules.kpis.domain.enums import KpiType
from app.modules.kpis.domain.services import (
    ProductKpiInputs,
    compute_all,
    coverage_days,
    overstock_risk,
    stockout_risk,
    turnover,
)
from app.modules.recommendations.domain.enums import RecommendationPriority
from app.modules.recommendations.domain.services import (
    ReorderInputs,
    suggest_reorder,
)


def _daily(value: int, days: int) -> list[Decimal]:
    return [Decimal(value)] * days


# --- KPIs --------------------------------------------------------------------
def test_coverage_days() -> None:
    # 100 units, demand 10/day over 30 days -> 10 days of coverage
    inp = ProductKpiInputs(current_stock=100, daily_demand=_daily(10, 30), lead_time_days=5)
    assert coverage_days(inp) == Decimal("10.00")


def test_coverage_infinite_when_no_demand() -> None:
    inp = ProductKpiInputs(current_stock=50, daily_demand=_daily(0, 30), lead_time_days=5)
    assert coverage_days(inp) == Decimal("9999")


def test_stockout_risk_high_when_stock_below_lead_demand() -> None:
    # lead time 5 days * 10/day = 50 needed; only 10 in stock -> high risk
    inp = ProductKpiInputs(current_stock=10, daily_demand=_daily(10, 30), lead_time_days=5)
    assert stockout_risk(inp) > Decimal("50")


def test_stockout_risk_zero_when_well_stocked() -> None:
    inp = ProductKpiInputs(current_stock=1000, daily_demand=_daily(10, 30), lead_time_days=5)
    assert stockout_risk(inp) == Decimal("0")


def test_turnover() -> None:
    # total demand 300, stock 100 -> turnover 3
    inp = ProductKpiInputs(current_stock=100, daily_demand=_daily(10, 30), lead_time_days=5)
    assert turnover(inp) == Decimal("3.0000")


def test_overstock_risk_when_excess() -> None:
    # 10/day: ~4 months need 1200; stock 5000 (500 days) -> heavy overstock
    inp = ProductKpiInputs(current_stock=5000, daily_demand=_daily(10, 30), lead_time_days=5)
    assert overstock_risk(inp) > Decimal("70")


def test_three_months_of_stock_is_not_overstock() -> None:
    inp = ProductKpiInputs(current_stock=1000, daily_demand=_daily(10, 30), lead_time_days=5)
    assert overstock_risk(inp) == Decimal("0")


def test_missing_lead_time_assumes_a_week() -> None:
    # No lead time recorded: 7 days + 7 review -> 140 needed; 60 on hand is a real risk.
    inp = ProductKpiInputs(current_stock=60, daily_demand=_daily(10, 30), lead_time_days=0)
    assert stockout_risk(inp) > Decimal("50")


def test_compute_all_returns_all_kpi_types() -> None:
    inp = ProductKpiInputs(current_stock=100, daily_demand=_daily(10, 30), lead_time_days=5)
    result = compute_all(inp)
    assert set(result.keys()) == set(KpiType)


# --- Reorder policy ----------------------------------------------------------
def test_suggest_reorder_triggers_when_low() -> None:
    inp = ReorderInputs(
        current_stock=5,
        daily_demand=_daily(10, 30),
        lead_time_days=5,
        safety_stock=20,
        reorder_point=60,
        review_days=7,
    )
    suggestion = suggest_reorder(inp)
    assert suggestion is not None
    # order-up-to = demand(12 days)=120 + safety 20 = 140; minus stock 5 -> 135
    assert suggestion.quantity == 135
    assert suggestion.priority == RecommendationPriority.HIGH


def test_suggest_reorder_none_when_sufficient() -> None:
    inp = ReorderInputs(
        current_stock=1000,
        daily_demand=_daily(10, 30),
        lead_time_days=5,
        safety_stock=20,
        reorder_point=60,
    )
    assert suggest_reorder(inp) is None


def test_suggest_reorder_priority_medium() -> None:
    # covers the supplier wait (50) but not wait + safety (70) -> buy this week
    inp = ReorderInputs(
        current_stock=60,
        daily_demand=_daily(10, 30),
        lead_time_days=5,
        safety_stock=20,
        reorder_point=60,
    )
    suggestion = suggest_reorder(inp)
    assert suggestion is not None
    assert suggestion.priority == RecommendationPriority.MEDIUM
