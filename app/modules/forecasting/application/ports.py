"""Forecasting module — application ports.

The FTGM Engine is an external service. The application depends on this port; the
concrete HTTP adapter lives in infrastructure/adapters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.modules.data_preparation.domain.entities import PreparedTimeSeries
from app.modules.data_preparation.domain.erp_analysis import ProductHistory
from app.modules.forecasting.domain.value_objects import ForecastPoint, HistoryPoint


@dataclass
class ProductForecast:
    """Forecast + accuracy metrics for a single product, as returned by the engine.

    Carries the full engine output: point forecast with interval, in-sample history
    (observed/cleaned/fitted), scaled metrics (MASE/RMSSE), the Fourier order chosen
    by Algorithm 1, which model actually ran, per-product status/reason, and the
    diagnostics (frequency decision, cleaning, hold-out validation, explanations).
    """

    product_id: UUID
    points: list[ForecastPoint]
    mape: Decimal | None
    mae: Decimal | None
    rmse: Decimal | None
    mase: Decimal | None = None
    rmsse: Decimal | None = None
    history: list[HistoryPoint] = field(default_factory=list)
    order_selected: int = 0
    model_used: str = ""
    status: str = "ok"
    fallback_reason: str | None = None
    validation_rmse: Decimal | None = None
    frequency: str | None = None
    period: int | None = None
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


class ForecastEnginePort(Protocol):
    """Port for the external FTGM forecasting engine."""

    def forecast(
        self,
        *,
        series: list[PreparedTimeSeries],
        horizon_days: int,
        model_name: str,
        frequency: str | None = None,
        as_of: date | None = None,
    ) -> list[ProductForecast]: ...


class ErpHistorySource(Protocol):
    """Read side of the ERP the scoped runs and insights need (adapter: ``ErpDataSource``).

    Products come back as the adapter's own rows; the use cases only read ``id``, ``sku``,
    ``name`` and the other plain attributes.
    """

    def resolve_scope(self, company_id: UUID, scope: dict[str, Any], as_of: date) -> list[Any]: ...

    def describe(self, company_id: UUID, scope: dict[str, Any], product_count: int) -> str: ...

    def load_histories(
        self, company_id: UUID, products: list[Any], as_of: date
    ) -> list[ProductHistory]: ...

    def sales_by_day(
        self, company_id: UUID, product_ids: list[UUID], start: date, end_exclusive: date
    ) -> dict[UUID, dict[date, int]]: ...

    def latest_runs(self, company_id: UUID, product_ids: list[UUID]) -> dict[UUID, dict[str, Any]]: ...

    def run_ids_for_product(self, company_id: UUID, product_id: UUID, limit: int = 20) -> list[UUID]: ...

    def products_by_ids(self, company_id: UUID, ids: list[UUID]) -> dict[UUID, Any]: ...

    def stock_map(self, company_id: UUID) -> dict[UUID, int]: ...
