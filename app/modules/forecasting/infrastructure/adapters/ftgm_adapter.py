"""FTGM Engine HTTP adapter (implements ForecastEnginePort).

Sends prepared series to the external FTGM Engine and parses its response. Network
or protocol failures propagate as exceptions so the calling use case can mark the run
as failed.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import math

import httpx

from app.config import settings
from app.modules.data_preparation.domain.entities import PreparedTimeSeries
from app.modules.forecasting.application.ports import ProductForecast
from app.modules.forecasting.domain.value_objects import ForecastPoint, HistoryPoint

# Approximate calendar length of one seasonal period, used to convert a horizon
# expressed in days into the number of periods the engine forecasts (legacy contract).
_DAYS_PER_PERIOD = {12: 30, 4: 91, 52: 7}


class FtgmHttpAdapter:
    """Calls POST {ftgm_engine_base_url}/forecast.

    Two contracts:

    * **frequency-aware** (``frequency`` given, used by ERP-scoped runs): sends
      ``frequency`` (auto/monthly/weekly), ``horizon_days`` and the ``as_of`` cut-off; the
      engine picks the bucket size per product and drops the period in progress.
    * **legacy** (CSV datasets): a fixed seasonal ``period`` and ``horizon`` in periods.

    Each series carries the stock-out flag so the engine can repair censored demand.
    When ``FTGM_ENGINE_API_KEY`` is configured the request carries ``X-Engine-Key`` (the
    engine rejects calls without it when its ``ENGINE_API_KEY`` is set).
    """

    #: Header the engine checks for the shared secret.
    API_KEY_HEADER = "X-Engine-Key"

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        period: int | None = None,
        api_key: str | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ftgm_engine_base_url).rstrip("/")
        # The configured timeout is respected as is (no hidden floor); guard only against
        # nonsensical values so a typo cannot disable the timeout altogether.
        configured = timeout if timeout is not None else float(settings.ftgm_engine_timeout_seconds)
        self._timeout = configured if configured > 0 else 180.0
        self._period = period or settings.ftgm_seasonal_period
        self._api_key = settings.ftgm_engine_api_key if api_key is None else api_key

    @property
    def timeout(self) -> float:
        return self._timeout

    def headers(self) -> dict[str, str]:
        return {self.API_KEY_HEADER: self._api_key} if self._api_key else {}

    def forecast(
        self,
        *,
        series: list[PreparedTimeSeries],
        horizon_days: int,
        model_name: str,
        frequency: str | None = None,
        as_of: date | None = None,
    ) -> list[ProductForecast]:
        payload: dict[str, Any] = {
            "model": model_name,
            "period": self._period,
            "series": [
                {
                    "product_id": str(s.product_id),
                    "points": [
                        {
                            "date": p.period_date.isoformat(),
                            "demand": str(p.demand),
                            "stockout_flag": p.is_stockout,
                        }
                        for p in s.points
                    ],
                }
                for s in series
            ],
        }
        if frequency:
            payload["frequency"] = frequency
            payload["horizon_days"] = horizon_days
            if as_of is not None:
                payload["as_of"] = as_of.isoformat()
        else:
            payload["horizon"] = self._days_to_periods(horizon_days)

        response = httpx.post(
            f"{self._base_url}/forecast",
            json=payload,
            headers=self.headers(),
            timeout=self._timeout,
        )
        response.raise_for_status()
        return [self._parse(item) for item in response.json().get("forecasts", [])]

    def _days_to_periods(self, horizon_days: int) -> int:
        """Convert a day horizon into a (rounded up) number of seasonal periods."""
        days_per_period = _DAYS_PER_PERIOD.get(self._period, 30)
        return max(1, math.ceil(horizon_days / days_per_period))

    @staticmethod
    def _optional_metric(metrics: dict[str, Any], key: str) -> Decimal | None:
        """Read a metric that may legitimately be absent (e.g. MAPE when every actual is 0,
        undefined MASE). Missing/null stays None: a 0 would read as a perfect forecast."""
        value = metrics.get(key)
        return Decimal(str(value)) if value is not None else None

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        return Decimal(str(value)) if value is not None else None

    @staticmethod
    def _parse(item: dict[str, Any]) -> ProductForecast:
        metrics = item.get("metrics", {})
        diagnostics = item.get("diagnostics") or {}
        return ProductForecast(
            product_id=UUID(str(item["product_id"])),
            points=[
                ForecastPoint(
                    period_date=date.fromisoformat(str(p["date"])),
                    predicted_demand=Decimal(str(p["predicted_demand"])),
                    lower_bound=(
                        Decimal(str(p["lower_bound"])) if p.get("lower_bound") is not None else None
                    ),
                    upper_bound=(
                        Decimal(str(p["upper_bound"])) if p.get("upper_bound") is not None else None
                    ),
                )
                for p in item.get("points", [])
            ],
            history=[
                HistoryPoint(
                    period_date=date.fromisoformat(str(h["date"])),
                    observed=Decimal(str(h["observed"])),
                    cleaned=Decimal(str(h["cleaned"])),
                    fitted=FtgmHttpAdapter._optional_decimal(h.get("fitted")),
                    is_stockout=bool(h.get("is_stockout", False)),
                    is_outlier=bool(h.get("is_outlier", False)),
                )
                for h in item.get("history", [])
            ],
            mape=FtgmHttpAdapter._optional_metric(metrics, "mape"),
            mae=FtgmHttpAdapter._optional_metric(metrics, "mae"),
            rmse=FtgmHttpAdapter._optional_metric(metrics, "rmse"),
            mase=FtgmHttpAdapter._optional_metric(metrics, "mase"),
            rmsse=FtgmHttpAdapter._optional_metric(metrics, "rmsse"),
            order_selected=int(item.get("order_selected", 0)),
            model_used=str(item.get("model", "")),
            status=str(item.get("status", "ok")),
            fallback_reason=(str(item["fallback_reason"])[:500] if item.get("fallback_reason") else None),
            validation_rmse=FtgmHttpAdapter._optional_decimal(diagnostics.get("validation_rmse")),
            frequency=item.get("frequency"),
            period=item.get("period"),
            warnings=list(item.get("warnings") or []),
            diagnostics=diagnostics,
        )
