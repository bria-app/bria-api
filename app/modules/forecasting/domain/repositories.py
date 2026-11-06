"""Forecasting module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.forecasting.domain.entities import (
    ForecastMetrics,
    ForecastResult,
    ForecastRun,
)


class ForecastRunRepository(Protocol):
    """Port for ForecastRun persistence."""

    def get_by_id(self, run_id: UUID) -> ForecastRun | None: ...
    def get_latest_by_company(self, company_id: UUID) -> ForecastRun | None: ...
    def list_by_company(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
        *,
        is_backtest: bool | None = None,
    ) -> list[ForecastRun]:
        """Newest first. ``is_backtest`` keeps only backtests (True) or only the others
        (False); None (default) returns every run."""
        ...
    def add(self, run: ForecastRun) -> ForecastRun: ...
    def update(self, run: ForecastRun) -> ForecastRun: ...


class ForecastResultRepository(Protocol):
    """Port for ForecastResult persistence."""

    def get_by_run_and_product(
        self, run_id: UUID, product_id: UUID
    ) -> ForecastResult | None: ...
    def list_by_run(self, run_id: UUID) -> list[ForecastResult]: ...
    def add(self, result: ForecastResult) -> ForecastResult: ...
    def add_bulk(self, results: list[ForecastResult]) -> list[ForecastResult]: ...


class ForecastMetricsRepository(Protocol):
    """Port for ForecastMetrics persistence."""

    def get_by_run_and_product(
        self, run_id: UUID, product_id: UUID
    ) -> ForecastMetrics | None: ...
    def list_by_run(self, run_id: UUID) -> list[ForecastMetrics]: ...
    def add(self, metrics: ForecastMetrics) -> ForecastMetrics: ...
    def add_bulk(self, metrics: list[ForecastMetrics]) -> list[ForecastMetrics]: ...
