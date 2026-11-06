"""Stock-out detection keeps empty shelves that lost demand and ignores the ones that did not."""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from app.modules.data_preparation.domain.erp_analysis import (
    EMPTY_SHELF_TAIL_DAYS,
    EMPTY_SHELF_UNASKED_DAYS,
    ProductHistory,
    detect_stockouts,
)


def _history(sold_days: int, empty_days: int) -> ProductHistory:
    """`sold_days` days selling 2 u/day from 20 units bought, then an empty shelf."""
    start = date(2026, 1, 1)
    h = ProductHistory(product_id=uuid4())
    h.moves[start] = 20
    for i in range(sold_days):
        d = start + timedelta(days=i)
        h.sales[d] = 2
        h.moves[d] = h.moves.get(d, 0) - 2
    h.on_hand = 20 - 2 * sold_days
    return h


def test_empty_shelf_nobody_asked_for_counts_only_its_first_days() -> None:
    h = _history(10, 0)  # sold out on day 10, then 60 days with nothing on the shelf
    as_of = date(2026, 1, 1) + timedelta(days=70)
    info = detect_stockouts(h, as_of)
    assert info.ledger_consistent
    assert len(info.days) == EMPTY_SHELF_UNASKED_DAYS


def test_lost_sales_inside_a_long_empty_run_flag_only_the_days_around_them() -> None:
    h = _history(10, 0)
    first_empty = date(2026, 1, 11)
    asked = first_empty + timedelta(days=40)  # one customer asked, off-season
    h.lost[asked] = (1, 1)
    info = detect_stockouts(h, first_empty + timedelta(days=120))
    expected = {first_empty + timedelta(days=i) for i in range(EMPTY_SHELF_UNASKED_DAYS)}
    expected |= {asked + timedelta(days=i) for i in range(EMPTY_SHELF_TAIL_DAYS + 1)}
    assert info.days == expected


def test_lost_sales_every_day_keep_the_whole_gap_censored() -> None:
    h = _history(10, 0)
    first_empty = date(2026, 1, 11)
    for i in range(21):  # the supplier failed for three weeks and people kept asking
        h.lost[first_empty + timedelta(days=i)] = (1, 2)
    info = detect_stockouts(h, first_empty + timedelta(days=60))
    assert {first_empty + timedelta(days=i) for i in range(21)} <= info.days


def test_lost_sale_days_are_always_stock_outs_even_without_a_ledger() -> None:
    h = ProductHistory(product_id=uuid4())
    h.sales[date(2026, 3, 2)] = 3
    h.lost[date(2026, 3, 5)] = (1, 1)
    info = detect_stockouts(h, date(2026, 4, 1))
    assert info.days == {date(2026, 3, 5)}
