"""Forecasting module — application output DTOs."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.modules.forecasting.domain.entities import (
    ForecastMetrics,
    ForecastResult,
    ForecastRun,
)


def run_engine_mode(run: ForecastRun) -> str:
    """"mock" (demo engine, simulated numbers) or "real". Runs older than the summary
    field are recognised by the mock's per-product ``diagnostics.engine`` marker."""
    mode = (run.meta.get("summary") or {}).get("ftgm_engine_mode")
    if mode:
        return str(mode)
    diagnostics = run.meta.get("diagnostics") or {}
    is_mock = any(isinstance(d, dict) and d.get("engine") == "mock" for d in diagnostics.values())
    return "mock" if is_mock else "real"


class ForecastRunDTO(BaseModel):
    id: UUID
    company_id: UUID
    dataset_id: UUID | None
    model_name: str
    horizon_days: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime | None = None
    # Scope (without internal metadata), what it covered and how it went.
    scope: dict[str, Any] | None = None
    scope_description: str | None = None
    frequency: str | None = None
    product_count: int = 0
    as_of: date | None = None
    # Cut-off in the past: a test of the model against what really sold, not a forecast to act on.
    is_backtest: bool = False
    summary: dict[str, Any] | None = None
    # "mock" = produced by the demo engine (simulated figures): the web shows a banner.
    ftgm_engine_mode: str = "real"

    @classmethod
    def from_entity(cls, run: ForecastRun) -> ForecastRunDTO:
        assert run.id is not None
        meta = run.meta
        scope = {k: v for k, v in (run.scope or {}).items() if k != "_meta"} or None
        as_of = meta.get("as_of")
        return cls(
            id=run.id,
            company_id=run.company_id,
            dataset_id=run.dataset_id,
            model_name=run.model_name,
            horizon_days=run.horizon_days,
            status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_message=run.error_message,
            created_at=run.created_at,
            scope=scope,
            scope_description=meta.get("description")
            or ("Dataset preparado (CSV)" if run.dataset_id and not scope else None),
            frequency=run.frequency,
            product_count=len(run.product_ids or []) or int(meta.get("product_count") or 0),
            as_of=date.fromisoformat(as_of) if as_of else None,
            is_backtest=run.is_backtest,
            summary=meta.get("summary"),
            ftgm_engine_mode=run_engine_mode(run),
        )


class ForecastPointDTO(BaseModel):
    period_date: date
    predicted_demand: Decimal
    lower_bound: Decimal | None
    upper_bound: Decimal | None


class HistoryPointDTO(BaseModel):
    period_date: date
    observed: Decimal
    cleaned: Decimal
    fitted: Decimal | None
    is_stockout: bool
    is_outlier: bool = False


class ForecastResultDTO(BaseModel):
    id: UUID
    run_id: UUID
    company_id: UUID
    product_id: UUID
    points: list[ForecastPointDTO]
    history: list[HistoryPointDTO] = []

    @classmethod
    def from_entity(cls, result: ForecastResult) -> ForecastResultDTO:
        assert result.id is not None
        return cls(
            id=result.id,
            run_id=result.run_id,
            company_id=result.company_id,
            product_id=result.product_id,
            points=[
                ForecastPointDTO(
                    period_date=p.period_date,
                    predicted_demand=p.predicted_demand,
                    lower_bound=p.lower_bound,
                    upper_bound=p.upper_bound,
                )
                for p in result.points
            ],
            history=[
                HistoryPointDTO(
                    period_date=h.period_date,
                    observed=h.observed,
                    cleaned=h.cleaned,
                    fitted=h.fitted,
                    is_stockout=h.is_stockout,
                    is_outlier=h.is_outlier,
                )
                for h in result.history
            ],
        )


class ForecastMetricsDTO(BaseModel):
    run_id: UUID
    product_id: UUID
    mape: Decimal | None
    mae: Decimal | None
    rmse: Decimal | None
    mase: Decimal | None = None
    rmsse: Decimal | None = None
    order_selected: int = 0
    model_used: str = ""
    status: str = "ok"
    fallback_reason: str | None = None
    validation_rmse: Decimal | None = None

    @classmethod
    def from_entity(cls, metrics: ForecastMetrics) -> ForecastMetricsDTO:
        return cls(
            run_id=metrics.run_id,
            product_id=metrics.product_id,
            mape=metrics.mape,
            mae=metrics.mae,
            rmse=metrics.rmse,
            mase=metrics.mase,
            rmsse=metrics.rmsse,
            order_selected=metrics.order_selected,
            model_used=metrics.model_used,
            status=metrics.status,
            fallback_reason=metrics.fallback_reason,
            validation_rmse=metrics.validation_rmse,
        )
