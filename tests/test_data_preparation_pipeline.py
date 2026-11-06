"""Bloque 3 — unit tests for the pure data-preparation service.

These import only the domain layer (no app.main), so they run even while other
modules are mid-implementation.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.modules.data_preparation.domain.services import prepare_demand_series
from app.modules.data_preparation.domain.value_objects import DemandRecord


def _rec(
    product_id: UUID, day: int, qty: int | str, stockout: bool = False
) -> DemandRecord:
    return DemandRecord(
        product_id=product_id,
        period_date=date(2026, 1, day),
        quantity=Decimal(str(qty)),
        is_stockout=stockout,
    )


def test_aggregates_quantity_by_date() -> None:
    pid = uuid4()
    result = prepare_demand_series([_rec(pid, 1, 3), _rec(pid, 1, 2)])
    assert len(result) == 1
    first = result[0].points[0]
    assert first.period_date == date(2026, 1, 1)
    assert first.demand == Decimal("5")


def test_fills_calendar_gaps_with_zero() -> None:
    pid = uuid4()
    # demand on day 1 and day 4 -> days 2 and 3 must be filled with 0
    result = prepare_demand_series([_rec(pid, 1, 10), _rec(pid, 4, 10)])
    points = result[0].points
    assert [p.period_date.day for p in points] == [1, 2, 3, 4]
    assert points[1].demand == Decimal("0")
    assert points[2].demand == Decimal("0")


def test_winsorizes_upper_outlier() -> None:
    pid = uuid4()
    # a clear spike on day 6 should be capped down by the IQR rule
    records = [_rec(pid, d, 10) for d in range(1, 6)] + [_rec(pid, 6, 1000)]
    result = prepare_demand_series(records)
    assert result[0].outliers_treated is True
    spike = result[0].points[-1]
    assert spike.demand < Decimal("1000")


def test_stockout_flag_for_zero_days_when_enabled() -> None:
    pid = uuid4()
    result = prepare_demand_series(
        [_rec(pid, 1, 10), _rec(pid, 3, 10)], treat_zero_as_stockout=True
    )
    points = result[0].points
    assert points[1].demand == Decimal("0")
    assert points[1].is_stockout is True
    assert result[0].has_stockout_flags is True


def test_no_stockout_flag_by_default() -> None:
    pid = uuid4()
    result = prepare_demand_series([_rec(pid, 1, 10), _rec(pid, 3, 10)])
    assert result[0].has_stockout_flags is False


def test_explicit_stockout_record_is_flagged() -> None:
    pid = uuid4()
    result = prepare_demand_series([_rec(pid, 1, 0, stockout=True)])
    assert result[0].points[0].is_stockout is True
