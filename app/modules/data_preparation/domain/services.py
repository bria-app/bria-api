"""Data preparation module domain — pure preparation service.

Turns raw demand observations into clean, model-ready time series. Steps per product:
1. Aggregate quantity by date.
2. Fill calendar gaps with zero-demand days (continuous daily series).
3. Treat upper outliers via the IQR rule (winsorize spikes to Q3 + 1.5*IQR).
4. Flag stockout days (zero-demand days, optionally) so the forecaster can treat them
   as missing rather than as genuine zero demand.

This is pure domain logic: no I/O, no frameworks. It works on ``DemandRecord`` (product
already resolved) and returns ``PreparedSeriesData`` per product.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.modules.data_preparation.domain.value_objects import (
    DemandRecord,
    SeriesPoint,
)

_OUTLIER_K = Decimal("1.5")
_MIN_POINTS_FOR_OUTLIERS = 4


@dataclass
class PreparedSeriesData:
    """Intermediate result of preparing one product's series."""

    product_id: UUID
    points: list[SeriesPoint] = field(default_factory=list)
    has_stockout_flags: bool = False
    outliers_treated: bool = False


def _upper_bound(values: list[Decimal]) -> Decimal | None:
    """IQR upper fence (Q3 + 1.5*IQR). None if too few points to be meaningful."""
    if len(values) < _MIN_POINTS_FOR_OUTLIERS:
        return None
    floats = [float(v) for v in values]
    q1, _, q3 = statistics.quantiles(floats, n=4)
    iqr = Decimal(str(q3)) - Decimal(str(q1))
    return Decimal(str(q3)) + _OUTLIER_K * iqr


def _prepare_one(
    product_id: UUID,
    records: list[DemandRecord],
    *,
    treat_zero_as_stockout: bool,
) -> PreparedSeriesData:
    # 1. Aggregate quantity by date; remember explicitly-flagged stockout dates.
    by_date: dict[date, Decimal] = {}
    flagged: set[date] = set()
    for r in records:
        by_date[r.period_date] = by_date.get(r.period_date, Decimal("0")) + r.quantity
        if r.is_stockout:
            flagged.add(r.period_date)

    if not by_date:
        return PreparedSeriesData(product_id=product_id)

    # 2. Build a continuous daily calendar, filling gaps with zero demand.
    start, end = min(by_date), max(by_date)
    calendar: list[date] = []
    cursor = start
    while cursor <= end:
        calendar.append(cursor)
        cursor += timedelta(days=1)

    demands = [by_date.get(d, Decimal("0")) for d in calendar]

    # 3. Winsorize upper outliers (spikes) using the IQR fence.
    bound = _upper_bound([v for v in demands if v > 0])
    outliers_treated = False
    if bound is not None:
        capped: list[Decimal] = []
        for v in demands:
            if v > bound:
                capped.append(bound)
                outliers_treated = True
            else:
                capped.append(v)
        demands = capped

    # 4. Flag stockout days.
    points: list[SeriesPoint] = []
    has_flags = False
    for d, demand in zip(calendar, demands, strict=True):
        is_stockout = d in flagged or (treat_zero_as_stockout and demand == 0)
        has_flags = has_flags or is_stockout
        points.append(SeriesPoint(period_date=d, demand=demand, is_stockout=is_stockout))

    return PreparedSeriesData(
        product_id=product_id,
        points=points,
        has_stockout_flags=has_flags,
        outliers_treated=outliers_treated,
    )


def prepare_demand_series(
    records: list[DemandRecord],
    *,
    treat_zero_as_stockout: bool = False,
) -> list[PreparedSeriesData]:
    """Group records by product and prepare each product's clean series."""
    grouped: dict[UUID, list[DemandRecord]] = {}
    for record in records:
        grouped.setdefault(record.product_id, []).append(record)
    return [
        _prepare_one(pid, recs, treat_zero_as_stockout=treat_zero_as_stockout)
        for pid, recs in grouped.items()
    ]
