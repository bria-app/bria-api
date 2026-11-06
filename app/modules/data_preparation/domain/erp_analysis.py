"""Data preparation domain — build model-ready demand history from ERP records.

Pure logic (no I/O). Input is one :class:`ProductHistory` per product, already loaded
from the ERP tables (sales, lost sales, inventory movements, purchases). Output:

* :func:`analyze` — the "Antes de pronosticar" analysis: history span, periods, units,
  zero share, stock-outs (lost sales at the till + the empty-shelf days around them, see
  :func:`detect_stockouts`), restocks, readiness for the FTGM with a plain-Spanish reason.
* :func:`build_points` — sparse daily observations for the engine: every day with sales
  plus every stock-out day (demand 0, flagged), strictly before the cut-off. The engine
  buckets them, drops the period in progress and repairs censored demand.

Readiness mirrors the engine's frequency rules so what the user sees before launching is
what the engine will actually do.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.modules.data_preparation.domain.value_objects import SeriesPoint
from decimal import Decimal

MIN_MONTHS_MONTHLY = 24
MIN_WEEKS_WEEKLY = 26
MIN_MONTHS_FIXED_MONTHLY = 12
INTERMITTENT_ZERO_SHARE = 0.5
STOCKOUT_BUCKET_SHARE = 0.10
#: The movement ledger is trusted for stock reconstruction only when its outbound units
#: explain at least this share of the units sold in the same window.
LEDGER_CONSISTENCY = 0.5
#: An empty shelf counts as lost demand for its first days (right after selling out) ...
EMPTY_SHELF_UNASKED_DAYS = 7
#: ... and for this many days after each lost sale registered at the till.
EMPTY_SHELF_TAIL_DAYS = 3
SPARKLINE_MONTHS = 24

READY = "listo"
LOW_DATA = "pocos_datos"
NO_SALES = "sin_ventas"
#: Has sales, but all of them fall in the period still in progress (e.g. a brand-new
#: account that sold today). Nothing complete to model yet — not the same as "no sales".
IN_PROGRESS = "en_curso"


# ----------------------------------------------------------------------------- periods
def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def next_month(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def bucket_start(d: date, frequency: str) -> date:
    return week_start(d) if frequency == "weekly" else month_start(d)


def next_bucket(d: date, frequency: str) -> date:
    return d + timedelta(days=7) if frequency == "weekly" else next_month(d)


def count_buckets(start: date, end_exclusive: date, frequency: str) -> int:
    """Number of complete buckets from the bucket of ``start`` up to ``end_exclusive``."""
    cursor = bucket_start(start, frequency)
    n = 0
    while next_bucket(cursor, frequency) <= end_exclusive:
        n += 1
        cursor = next_bucket(cursor, frequency)
    return n


def iter_buckets(start: date, end_exclusive: date, frequency: str) -> list[date]:
    out: list[date] = []
    cursor = bucket_start(start, frequency)
    while cursor < end_exclusive:
        out.append(cursor)
        cursor = next_bucket(cursor, frequency)
    return out


# ----------------------------------------------------------------------------- input
@dataclass
class ProductHistory:
    product_id: UUID
    sku: str = ""
    name: str = ""
    unit_cost: Decimal = Decimal("0")
    sales: dict[date, int] = field(default_factory=dict)  # units per day
    sales_count: int = 0  # sale lines
    lost: dict[date, tuple[int, int]] = field(default_factory=dict)  # (attempts, units)
    moves: dict[date, int] = field(default_factory=dict)  # signed units per day
    moves_count: int = 0
    purchases: list[tuple[date, int]] = field(default_factory=list)
    on_hand: int = 0


@dataclass
class StockoutInfo:
    days: set[date]
    ledger_consistent: bool
    ledger_start: date | None


def detect_stockouts(h: ProductHistory, as_of: date) -> StockoutInfo:
    """Stock-out days before ``as_of``: days with lost demand, not every empty shelf.

    A lost sale at the till is direct evidence. An empty shelf in the ledger is evidence
    only near it: the first days of a run of empty days, and a few days after each lost
    sale inside the run. A shop that does not carry a
    product off-season (winter coats in summer, costumes after Halloween) has an empty
    shelf for months without losing a sale; reading those months as censored demand would
    rebuild sales that never existed.
    """
    lost_days = {d for d in h.lost if d < as_of}
    days = set(lost_days)
    if not h.moves:
        return StockoutInfo(days, False, None)
    ledger_start = min(h.moves)
    moved_out = -sum(v for d, v in h.moves.items() if v < 0 and d < as_of)
    sold = sum(u for d, u in h.sales.items() if ledger_start <= d < as_of)
    consistent = sold > 0 and moved_out >= LEDGER_CONSISTENCY * sold
    if consistent:
        balance = 0
        cursor = ledger_start
        empty_run: list[date] = []
        while cursor < as_of:
            opening = balance
            balance += h.moves.get(cursor, 0)
            if opening <= 0 and h.sales.get(cursor, 0) == 0 and cursor > ledger_start:
                empty_run.append(cursor)
            elif empty_run:
                days.update(_censored_part(empty_run, lost_days))
                empty_run = []
            cursor += timedelta(days=1)
        if empty_run:
            days.update(_censored_part(empty_run, lost_days))
    return StockoutInfo(days, consistent, ledger_start)


def _censored_part(run: list[date], lost_days: set[date]) -> list[date]:
    """The days of an empty-shelf run that most likely lost demand (see detect_stockouts).

    Evidence is local: the first days of the run (right after selling out) and a few days
    after each lost sale. One customer asking for a costume in August is one lost sale,
    not proof that the whole off-season since November lost demand.
    """
    tail = timedelta(days=EMPTY_SHELF_TAIL_DAYS)
    asked = sorted(d for d in run if d in lost_days)
    return [
        d for i, d in enumerate(run)
        if i < EMPTY_SHELF_UNASKED_DAYS or any(a <= d <= a + tail for a in asked)
    ]


def stock_levels(h: ProductHistory, info: StockoutInfo, buckets: list[date], frequency: str) -> dict[date, int | None]:
    """End-of-bucket on-hand from the ledger (None where the ledger is not reliable)."""
    out: dict[date, int | None] = {b: None for b in buckets}
    if not info.ledger_consistent or info.ledger_start is None:
        return out
    ordered = sorted(h.moves.items())
    idx, balance = 0, 0
    for b in buckets:
        end = next_bucket(b, frequency)
        while idx < len(ordered) and ordered[idx][0] < end:
            balance += ordered[idx][1]
            idx += 1
        out[b] = balance if end > info.ledger_start else None
    return out


# ----------------------------------------------------------------------------- analysis
def _choose_frequency(requested: str, months: int, weeks: int) -> tuple[str, str]:
    if requested == "monthly":
        return "monthly", "Frecuencia mensual elegida."
    if requested == "weekly":
        return "weekly", "Frecuencia semanal elegida."
    if months >= MIN_MONTHS_MONTHLY:
        return "monthly", f"{months} meses completos (≥ {MIN_MONTHS_MONTHLY}) → mensual."
    if weeks >= MIN_WEEKS_WEEKLY:
        return "weekly", f"{months} meses (< {MIN_MONTHS_MONTHLY}) pero {weeks} semanas (≥ {MIN_WEEKS_WEEKLY}) → semanal."
    return "weekly", f"Solo {weeks} semanas completas (< {MIN_WEEKS_WEEKLY})."


def analyze(h: ProductHistory, as_of: date, requested_frequency: str = "auto") -> dict[str, Any]:
    """Per-product readiness analysis (see module docstring)."""
    # What the model can use (strictly before the cut-off) vs. everything sold up to the
    # cut-off day — today's POS sales must show up in the counts even though the period
    # they belong to is still open.
    sale_days = sorted(d for d, u in h.sales.items() if u > 0 and d < as_of)
    shown_days = sorted(d for d, u in h.sales.items() if u > 0 and d <= as_of)
    info = detect_stockouts(h, as_of)
    purchases = sorted((d, q) for d, q in h.purchases if d < as_of + timedelta(days=1))
    lost_attempts = sum(a for d, (a, _) in h.lost.items() if d < as_of)
    lost_units = sum(u for d, (_, u) in h.lost.items() if d < as_of)
    base: dict[str, Any] = {
        "product_id": str(h.product_id),
        "sku": h.sku,
        "name": h.name,
        "unit_cost": float(h.unit_cost),
        "on_hand": h.on_hand,
        "first_sale": shown_days[0].isoformat() if shown_days else None,
        "last_sale": shown_days[-1].isoformat() if shown_days else None,
        "total_units": int(sum(h.sales.get(d, 0) for d in shown_days)),
        "sales_count": h.sales_count,
        "stockout_days": len(info.days),
        "lost_sale_attempts": lost_attempts,
        "lost_units": lost_units,
        "restocks_count": len(purchases),
        "last_restock_date": purchases[-1][0].isoformat() if purchases else None,
        "last_restock_qty": purchases[-1][1] if purchases else None,
        "movements_count": h.moves_count,
        "ledger_reliable": info.ledger_consistent,
        "frequency": None,
        "frequency_reason": None,
        "periods": 0,
        "periods_with_data": 0,
        "avg_per_period": 0.0,
        "zero_share": None,
        "stockout_periods": 0,
        "monthly_series": [],
        "readiness": NO_SALES,
        "included": False,
        "model_hint": None,
        "reason": "",
    }

    current_month = month_start(as_of)
    sparkline_start = current_month
    for _ in range(SPARKLINE_MONTHS):
        sparkline_start = month_start(sparkline_start - timedelta(days=1))
    monthly: dict[date, int] = {}
    for d in sale_days:
        if sparkline_start <= d < current_month:
            k = month_start(d)
            monthly[k] = monthly.get(k, 0) + h.sales[d]
    base["monthly_series"] = [
        {"period": b.isoformat(), "units": monthly.get(b, 0)} for b in iter_buckets(sparkline_start, current_month, "monthly")
    ]

    if not shown_days:
        base["reason"] = "Sin ventas registradas: no hay demanda que modelar. Se excluye."
        return base
    if not sale_days:
        base.update(readiness=IN_PROGRESS, reason=_in_progress_reason(h, shown_days, as_of, requested_frequency))
        return base

    first = sale_days[0]
    months = count_buckets(first, current_month, "monthly")
    weeks = count_buckets(first, week_start(as_of), "weekly")
    frequency, freq_reason = _choose_frequency(requested_frequency, months, weeks)
    cutoff = bucket_start(as_of, frequency)
    buckets = [b for b in iter_buckets(first, cutoff, frequency)]
    base["frequency"] = frequency
    base["frequency_reason"] = freq_reason

    if not buckets:
        base.update(readiness=IN_PROGRESS, reason=_in_progress_reason(h, shown_days, as_of, frequency))
        return base

    units: dict[date, int] = {}
    for d in sale_days:
        if d < cutoff:
            k = bucket_start(d, frequency)
            units[k] = units.get(k, 0) + h.sales[d]
    stock_days: dict[date, int] = {}
    for d in info.days:
        if d < cutoff:
            k = bucket_start(d, frequency)
            stock_days[k] = stock_days.get(k, 0) + 1
    stockout_periods = sum(
        1 for b in buckets if stock_days.get(b, 0) / max(1, (next_bucket(b, frequency) - b).days) >= STOCKOUT_BUCKET_SHARE
    )
    with_data = sum(1 for b in buckets if units.get(b, 0) > 0)
    zero_share = 1.0 - with_data / len(buckets)
    total = sum(units.values())
    base.update(
        periods=len(buckets),
        periods_with_data=with_data,
        avg_per_period=round(total / len(buckets), 2),
        zero_share=round(zero_share, 3),
        stockout_periods=stockout_periods,
        included=True,
    )

    word = "semanas" if frequency == "weekly" else "meses"
    if len(buckets) >= 4 and zero_share > INTERMITTENT_ZERO_SHARE:
        base.update(
            readiness=LOW_DATA,
            model_hint="CrostonSBA",
            reason=f"Demanda intermitente: {zero_share * 100:.0f}% de {word} sin ventas → baseline Croston-SBA.",
        )
    elif requested_frequency == "auto" and months < MIN_MONTHS_MONTHLY and weeks < MIN_WEEKS_WEEKLY:
        base.update(
            readiness=LOW_DATA,
            model_hint="MovingAverage",
            reason=f"Solo {weeks} semanas de historia (< {MIN_WEEKS_WEEKLY}) → baseline de promedio móvil.",
        )
    elif (frequency == "monthly" and len(buckets) < MIN_MONTHS_FIXED_MONTHLY) or (
        frequency == "weekly" and len(buckets) < MIN_WEEKS_WEEKLY
    ):
        base.update(
            readiness=LOW_DATA,
            model_hint="SeasonalNaive",
            reason=f"Solo {len(buckets)} {word} completos: muy poco para el FTGM → baseline estacional.",
        )
    else:
        extra = f" {stockout_periods} {word} con quiebre se repararán." if stockout_periods else ""
        base.update(
            readiness=READY,
            model_hint="FTGM",
            reason=f"{len(buckets)} {word} de historia, {with_data} con ventas.{extra}",
        )
    return base


def _in_progress_reason(h: ProductHistory, days: list[date], as_of: date, frequency: str) -> str:
    """Plain-Spanish explanation for sales that only exist in the period still open."""
    n = int(sum(h.sales.get(d, 0) for d in days))
    if frequency == "monthly":
        start, word = month_start(as_of), "el mes en curso"
        joins, unit = next_month(start), "meses completos"
    else:
        start, word = week_start(as_of), "la semana en curso"
        joins, unit = start + timedelta(days=7), "semanas completas"
    return (
        f"{n} unidad(es) vendidas en {word} (desde el {start:%d/%m}). El motor solo usa {unit}: "
        f"estas ventas entrarán el {joins:%d/%m/%Y}. Para pronosticar hoy, importa tu historial "
        "en Ventas › Historial importado (con 1 semana completa usa un baseline; con 26 semanas, el FTGM)."
    )


def build_points(h: ProductHistory, as_of: date) -> list[SeriesPoint]:
    """Sparse daily observations (< as_of): sales days + flagged stock-out days."""
    info = detect_stockouts(h, as_of)
    days = {d for d, u in h.sales.items() if u > 0 and d < as_of} | info.days
    return [
        SeriesPoint(period_date=d, demand=Decimal(h.sales.get(d, 0)), is_stockout=d in info.days)
        for d in sorted(days)
    ]


def consolidate(rows: list[dict[str, Any]], requested_frequency: str, as_of: date) -> dict[str, Any]:
    included = [r for r in rows if r["included"]]
    excluded = [r for r in rows if not r["included"]]
    freqs = {r["frequency"] for r in included if r["frequency"]}
    if requested_frequency in ("monthly", "weekly"):
        chosen = requested_frequency
    elif len(freqs) == 1:
        chosen = next(iter(freqs))
    elif freqs:
        chosen = "mixed"
    else:
        chosen = None
    firsts = [r["first_sale"] for r in included if r["first_sale"]]
    return {
        "as_of": as_of.isoformat(),
        "requested_frequency": requested_frequency,
        "frequency": chosen,
        "products_total": len(rows),
        "products_included": len(included),
        "products_excluded": len(excluded),
        "products_ready": sum(1 for r in included if r["readiness"] == READY),
        "products_low_data": sum(1 for r in included if r["readiness"] == LOW_DATA),
        "total_data_points": sum(r["periods"] for r in included),
        "max_periods": max((r["periods"] for r in included), default=0),
        "total_units": sum(r["total_units"] for r in included),
        "date_start": min(firsts) if firsts else None,
        "date_end": (as_of - timedelta(days=1)).isoformat(),
        "excluded": [{"product_id": r["product_id"], "name": r["name"], "reason": r["reason"]} for r in excluded],
    }
