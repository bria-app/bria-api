"""Forecasting domain — forecast vs actual tracking (pure).

For each forecast period we compare the prediction with the demand actually sold in the
same calendar bucket, up to ``today``. The period in progress is *partial*: its forecast
is prorated by the elapsed share of days so the comparison is fair mid-period.

* error to date — MAPE on complete periods (with sales) and bias % on everything elapsed
  (``(forecast_to_date - actual) / actual``);
* status — ``en_linea`` (|bias| <= 15%), ``sobre_pronostico`` (forecast above actual),
  ``bajo_pronostico`` (actual above forecast) or ``pendiente`` (no period elapsed yet).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.modules.forecasting.domain.value_objects import ForecastPoint

BIAS_TOLERANCE_PCT = 15.0

ON_TRACK = "en_linea"
OVER = "sobre_pronostico"
UNDER = "bajo_pronostico"
PENDING = "pendiente"


def infer_frequency(points: list[ForecastPoint], fallback: str | None = None) -> str:
    if len(points) >= 2:
        gap = (points[1].period_date - points[0].period_date).days
        return "weekly" if gap <= 8 else "monthly"
    if fallback in ("weekly", "monthly"):
        return fallback
    return "weekly" if points and points[0].period_date.weekday() == 0 and points[0].period_date.day != 1 else "monthly"


def period_end(start: date, frequency: str) -> date:
    """Exclusive end of the bucket starting at ``start``."""
    if frequency == "weekly":
        return start + timedelta(days=7)
    return date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)


def track_product(
    points: list[ForecastPoint],
    frequency: str,
    sales_by_day: dict[date, int],
    today: date,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    cum_fc = cum_act = 0.0
    for p in points:
        start, end = p.period_date, period_end(p.period_date, frequency)
        forecast = float(p.predicted_demand)
        row: dict[str, Any] = {
            "period": start.isoformat(),
            "period_end": (end - timedelta(days=1)).isoformat(),
            "forecast": round(forecast, 2),
            "lower": float(p.lower_bound) if p.lower_bound is not None else None,
            "upper": float(p.upper_bound) if p.upper_bound is not None else None,
            "actual": None,
            "partial": False,
            "elapsed_share": 0.0,
            "forecast_to_date": None,
            "cum_forecast": None,
            "cum_actual": None,
            "within_band": None,
        }
        if start <= today:
            upto = min(end, today + timedelta(days=1))
            actual = sum(u for d, u in sales_by_day.items() if start <= d < upto)
            total_days = max(1, (end - start).days)
            share = min(1.0, (upto - start).days / total_days)
            partial = upto < end
            to_date = forecast * share
            cum_fc += to_date
            cum_act += actual
            row.update(
                actual=actual,
                partial=partial,
                elapsed_share=round(share, 3),
                forecast_to_date=round(to_date, 2),
                cum_forecast=round(cum_fc, 2),
                cum_actual=round(cum_act, 2),
            )
            if not partial and row["lower"] is not None and row["upper"] is not None:
                row["within_band"] = row["lower"] <= actual <= row["upper"]
        rows.append(row)

    elapsed = [r for r in rows if r["actual"] is not None]
    complete = [r for r in elapsed if not r["partial"]]
    mape_rows = [r for r in complete if r["actual"] > 0]
    mape = (
        round(sum(abs(r["forecast"] - r["actual"]) / r["actual"] for r in mape_rows) / len(mape_rows) * 100, 2)
        if mape_rows
        else None
    )
    bias = round((cum_fc - cum_act) / cum_act * 100, 2) if cum_act > 0 else None
    if not elapsed:
        status = PENDING
    elif bias is None:
        status = OVER if cum_fc > 0.5 else ON_TRACK
    elif abs(bias) <= BIAS_TOLERANCE_PCT:
        status = ON_TRACK
    elif bias > 0:
        status = OVER
    else:
        status = UNDER
    band = [r["within_band"] for r in complete if r["within_band"] is not None]
    return {
        "frequency": frequency,
        "rows": rows,
        "periods_total": len(rows),
        "periods_elapsed": len(elapsed),
        "periods_complete": len(complete),
        "forecast_to_date": round(cum_fc, 2),
        "actual_to_date": round(cum_act, 2),
        "mape": mape,
        "bias_pct": bias,
        "within_band_share": round(sum(band) / len(band), 3) if band else None,
        "status": status,
    }
