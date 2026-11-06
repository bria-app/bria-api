"""Forecasting module — SQLAlchemy repository implementations."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.forecasting.domain.entities import (
    ForecastMetrics,
    ForecastResult,
    ForecastRun,
)
from app.modules.forecasting.domain.exceptions import ForecastRunNotFoundError
from app.modules.forecasting.infrastructure.persistence.mappers import (
    metrics_to_entity,
    metrics_to_model,
    result_to_entity,
    result_to_model,
    run_to_entity,
    run_to_model,
)
from app.modules.forecasting.infrastructure.persistence.models import (
    ForecastMetricsModel,
    ForecastResultModel,
    ForecastRunModel,
)


class SqlForecastRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, run_id: UUID) -> ForecastRun | None:
        model = self._session.get(ForecastRunModel, run_id)
        return run_to_entity(model) if model else None

    def get_latest_by_company(self, company_id: UUID) -> ForecastRun | None:
        model = self._session.execute(
            select(ForecastRunModel)
            .where(ForecastRunModel.company_id == company_id)
            .order_by(ForecastRunModel.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return run_to_entity(model) if model else None

    def list_by_company(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
        *,
        is_backtest: bool | None = None,
    ) -> list[ForecastRun]:
        stmt = (
            select(ForecastRunModel)
            .where(ForecastRunModel.company_id == company_id)
            .order_by(ForecastRunModel.created_at.desc())
        )
        if is_backtest is None:
            rows = self._session.execute(stmt.offset(offset).limit(limit)).scalars().all()
            return [run_to_entity(m) for m in rows]
        # The flag lives inside the JSON scope (scope["_meta"]["backtest"]); it is read
        # through the entity so SQLite and Postgres agree, then the page is cut. A company
        # has few runs (the plan caps them per month), so this stays small.
        runs = [
            run
            for run in (run_to_entity(m) for m in self._session.execute(stmt).scalars())
            if run.is_backtest == is_backtest
        ]
        return runs[offset : offset + limit]

    def add(self, run: ForecastRun) -> ForecastRun:
        model = run_to_model(run)
        self._session.add(model)
        self._session.flush()
        return run_to_entity(model)

    def update(self, run: ForecastRun) -> ForecastRun:
        model = self._session.get(ForecastRunModel, run.id)
        if model is None:
            raise ForecastRunNotFoundError(message="No encontramos ese pronóstico. Actualiza la página e inténtalo de nuevo.")
        model.dataset_id = run.dataset_id
        model.model_name = run.model_name
        model.horizon_days = run.horizon_days
        model.status = run.status.value
        model.started_at = run.started_at
        model.completed_at = run.completed_at
        model.error_message = run.error_message
        # Reassign (never mutate in place) so SQLAlchemy detects the JSON change.
        model.scope = dict(run.scope) if run.scope is not None else None
        model.product_ids = list(run.product_ids) if run.product_ids is not None else None
        model.frequency = run.frequency
        self._session.flush()
        return run_to_entity(model)


class SqlForecastResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_run_and_product(
        self, run_id: UUID, product_id: UUID
    ) -> ForecastResult | None:
        model = self._session.execute(
            select(ForecastResultModel).where(
                ForecastResultModel.run_id == run_id,
                ForecastResultModel.product_id == product_id,
            )
        ).scalar_one_or_none()
        return result_to_entity(model) if model else None

    def list_by_run(self, run_id: UUID) -> list[ForecastResult]:
        rows = self._session.execute(
            select(ForecastResultModel).where(ForecastResultModel.run_id == run_id)
        ).scalars().all()
        return [result_to_entity(m) for m in rows]

    def add(self, result: ForecastResult) -> ForecastResult:
        model = result_to_model(result)
        self._session.add(model)
        self._session.flush()
        return result_to_entity(model)

    def add_bulk(self, results: list[ForecastResult]) -> list[ForecastResult]:
        models = [result_to_model(r) for r in results]
        self._session.add_all(models)
        self._session.flush()
        return [result_to_entity(m) for m in models]


class SqlForecastMetricsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_run_and_product(
        self, run_id: UUID, product_id: UUID
    ) -> ForecastMetrics | None:
        model = self._session.execute(
            select(ForecastMetricsModel).where(
                ForecastMetricsModel.run_id == run_id,
                ForecastMetricsModel.product_id == product_id,
            )
        ).scalar_one_or_none()
        return metrics_to_entity(model) if model else None

    def list_by_run(self, run_id: UUID) -> list[ForecastMetrics]:
        rows = self._session.execute(
            select(ForecastMetricsModel).where(ForecastMetricsModel.run_id == run_id)
        ).scalars().all()
        return [metrics_to_entity(m) for m in rows]

    def add(self, metrics: ForecastMetrics) -> ForecastMetrics:
        model = metrics_to_model(metrics)
        self._session.add(model)
        self._session.flush()
        return metrics_to_entity(model)

    def add_bulk(self, metrics: list[ForecastMetrics]) -> list[ForecastMetrics]:
        models = [metrics_to_model(m) for m in metrics]
        self._session.add_all(models)
        self._session.flush()
        return [metrics_to_entity(m) for m in models]
