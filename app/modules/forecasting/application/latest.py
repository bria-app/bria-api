"""Forecasting — the freshest forecast per product across runs.

Runs can cover a single product (free plan), a supplier, a category… so "the latest
run" is not enough for the decision layer: each product uses the most recent successful
run that actually forecast it. Period length is read from the forecast dates themselves
(monthly or weekly buckets), so KPIs and recommendations turn per-period demand into
daily demand correctly for any frequency.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.modules.forecasting.domain.entities import ForecastResult, ForecastRun
from app.modules.forecasting.domain.enums import RunStatus
from app.modules.forecasting.domain.repositories import (
    ForecastResultRepository,
    ForecastRunRepository,
)
from app.modules.forecasting.domain.value_objects import ForecastPoint

_MONTH_DAYS = 30.4375


def latest_results_by_product(
    runs: ForecastRunRepository,
    results: ForecastResultRepository,
    company_id: UUID,
    limit: int = 50,
) -> dict[UUID, tuple[ForecastRun, ForecastResult]]:
    out: dict[UUID, tuple[ForecastRun, ForecastResult]] = {}
    for run in runs.list_by_company(company_id, 0, limit):  # newest first
        if run.status != RunStatus.SUCCESS or run.id is None or run.is_backtest:
            continue
        for result in results.list_by_run(run.id):
            if result.points and result.product_id not in out:
                out[result.product_id] = (run, result)
    return out


def days_per_period(points: list[ForecastPoint], frequency: str | None = None) -> float:
    if len(points) >= 2:
        gap = (points[1].period_date - points[0].period_date).days
        return 7.0 if gap <= 8 else _MONTH_DAYS
    return 7.0 if frequency == "weekly" else _MONTH_DAYS


def to_daily_demand(points: list[ForecastPoint], frequency: str | None = None) -> list[Decimal]:
    """Spread each period's forecast evenly over its days (flat daily-demand series)."""
    period_days = days_per_period(points, frequency)
    span = max(1, round(period_days))
    divisor = Decimal(str(period_days))
    daily: list[Decimal] = []
    for p in points:
        rate = (p.predicted_demand / divisor).quantize(Decimal("0.0001"))
        daily.extend([rate] * span)
    return daily
