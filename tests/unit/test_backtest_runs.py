"""Backtest runs (cut-off in the past) check the model; they never feed today's decisions."""
from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.modules.forecasting.application.dtos import ForecastRunDTO
from app.modules.forecasting.application.latest import latest_results_by_product
from app.modules.forecasting.domain.entities import ForecastResult, ForecastRun, RunStatus
from app.modules.forecasting.domain.value_objects import ForecastPoint


def _run(backtest: bool) -> ForecastRun:
    return ForecastRun(
        company_id=uuid4(), model_name="FTGM", horizon_days=90, status=RunStatus.SUCCESS, id=uuid4(),
        scope={"type": "all", "_meta": {"as_of": "2026-08-01", "backtest": backtest}},
    )


class _Runs:
    def __init__(self, runs):
        self.runs = runs

    def list_by_company(self, company_id, offset, limit):
        return self.runs


class _Results:
    def __init__(self, by_run):
        self.by_run = by_run

    def list_by_run(self, run_id):
        return self.by_run.get(run_id, [])


def test_flag_reaches_entity_and_dto():
    assert _run(True).is_backtest
    assert not _run(False).is_backtest
    assert ForecastRun(company_id=uuid4(), model_name="FTGM", horizon_days=30).is_backtest is False
    assert ForecastRunDTO.from_entity(_run(True)).is_backtest is True


def test_latest_forecast_skips_backtests():
    pid = uuid4()
    point = ForecastPoint(period_date=date(2026, 8, 1), predicted_demand=5, lower_bound=1, upper_bound=9)
    today, past = _run(False), _run(True)
    results = _Results({
        today.id: [ForecastResult(run_id=today.id, company_id=today.company_id, product_id=pid, points=[point])],
        past.id: [ForecastResult(run_id=past.id, company_id=past.company_id, product_id=pid, points=[point])],
    })
    # The backtest is newer (first), but the latest forecast for the product is today's.
    latest = latest_results_by_product(_Runs([past, today]), results, today.company_id)
    assert latest[pid][0] is today
    assert latest_results_by_product(_Runs([past]), results, today.company_id) == {}
