"""Forecasting module domain — value objects."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ForecastPoint:
    """A single forecasted demand point."""

    period_date: date
    predicted_demand: Decimal
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None


@dataclass(frozen=True)
class HistoryPoint:
    """One in-sample period as consumed/produced by the engine.

    ``observed`` is the aggregated demand, ``cleaned`` the demand after stock-out
    imputation (what the model was fit on) and ``fitted`` the model's in-sample fit.
    Persisting these makes every run self-contained: the real-vs-model chart can be
    rebuilt without re-reading the source dataset (reproducibility).
    """

    period_date: date
    observed: Decimal
    cleaned: Decimal
    fitted: Decimal | None = None
    is_stockout: bool = False
    is_outlier: bool = False
