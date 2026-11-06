"""Forecasting module — run lifecycle use cases."""
from __future__ import annotations

from uuid import UUID

from app.modules.forecasting.application.dtos import (
    ForecastMetricsDTO,
    ForecastResultDTO,
    ForecastRunDTO,
)
from app.modules.data_preparation.domain.enums import DatasetStatus
from app.modules.data_preparation.domain.repositories import PreparedDatasetRepository
from app.modules.forecasting.domain.entities import ForecastRun
from app.modules.forecasting.domain.exceptions import ForecastRunNotFoundError
from app.modules.forecasting.domain.repositories import (
    ForecastMetricsRepository,
    ForecastResultRepository,
    ForecastRunRepository,
)
from app.shared.domain.errors import ValidationError


class CreateForecastRun:
    """Create a run bound to a *valid* prepared dataset.

    The dataset is resolved eagerly so misconfiguration fails at creation time with a
    clear message — never asynchronously inside the background job:

    * ``dataset_id`` given  -> it must exist, belong to the company and be READY.
    * ``dataset_id`` absent -> default to the company's most recent READY dataset.
    """

    def __init__(
        self,
        runs: ForecastRunRepository,
        datasets: PreparedDatasetRepository,
    ) -> None:
        self._runs = runs
        self._datasets = datasets

    def execute(
        self,
        company_id: UUID,
        *,
        model_name: str,
        horizon_days: int,
        dataset_id: UUID | None = None,
    ) -> ForecastRunDTO:
        resolved = self._resolve_dataset(company_id, dataset_id)
        run = ForecastRun(
            company_id=company_id,
            model_name=model_name,
            horizon_days=horizon_days,
            dataset_id=resolved,
        )
        return ForecastRunDTO.from_entity(self._runs.add(run))

    def _resolve_dataset(self, company_id: UUID, dataset_id: UUID | None) -> UUID:
        if dataset_id is not None:
            dataset = self._datasets.get_by_id(dataset_id)
            if dataset is None or dataset.company_id != company_id:
                raise ValidationError(
                    message=f"El dataset '{dataset_id}' no existe para esta empresa."
                )
            if dataset.status != DatasetStatus.READY:
                raise ValidationError(
                    message=(
                        f"El dataset '{dataset_id}' no está listo "
                        f"(estado: {dataset.status.value})."
                    )
                )
            assert dataset.id is not None
            return dataset.id

        latest_ready = next(
            (
                d
                for d in self._datasets.list_by_company(company_id)
                if d.status == DatasetStatus.READY and d.id is not None
            ),
            None,
        )
        if latest_ready is None:
            raise ValidationError(
                message=(
                    "No hay ningún dataset preparado. Ve a Ingesta, sube tus ventas y "
                    "ejecuta 'Preparar dataset' antes de crear un pronóstico."
                )
            )
        assert latest_ready.id is not None
        return latest_ready.id


def owned_run(runs: ForecastRunRepository, company_id: UUID, run_id: UUID) -> ForecastRun:
    """Load a run of ``company_id``; another company's run is reported as missing (404)."""
    run = runs.get_by_id(run_id)
    if run is None or run.company_id != company_id:
        raise ForecastRunNotFoundError(message="No encontramos ese pronóstico. Actualiza la página e inténtalo de nuevo.")
    return run


class GetForecastRun:
    def __init__(self, runs: ForecastRunRepository) -> None:
        self._runs = runs

    def execute(self, company_id: UUID, run_id: UUID) -> ForecastRunDTO:
        return ForecastRunDTO.from_entity(owned_run(self._runs, company_id, run_id))


class ListForecastRuns:
    def __init__(self, runs: ForecastRunRepository) -> None:
        self._runs = runs

    def execute(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
        is_backtest: bool | None = None,
    ) -> list[ForecastRunDTO]:
        runs = (
            self._runs.list_by_company(company_id, offset, limit)
            if is_backtest is None
            else self._runs.list_by_company(company_id, offset, limit, is_backtest=is_backtest)
        )
        return [ForecastRunDTO.from_entity(r) for r in runs]


class CancelForecastRun:
    def __init__(self, runs: ForecastRunRepository) -> None:
        self._runs = runs

    def execute(self, company_id: UUID, run_id: UUID) -> ForecastRunDTO:
        run = owned_run(self._runs, company_id, run_id)
        run.cancel()
        return ForecastRunDTO.from_entity(self._runs.update(run))


class ListRunResults:
    def __init__(self, results: ForecastResultRepository, runs: ForecastRunRepository) -> None:
        self._results = results
        self._runs = runs

    def execute(self, company_id: UUID, run_id: UUID) -> list[ForecastResultDTO]:
        owned_run(self._runs, company_id, run_id)
        return [
            ForecastResultDTO.from_entity(r) for r in self._results.list_by_run(run_id)
        ]


class ListRunMetrics:
    def __init__(self, metrics: ForecastMetricsRepository, runs: ForecastRunRepository) -> None:
        self._metrics = metrics
        self._runs = runs

    def execute(self, company_id: UUID, run_id: UUID) -> list[ForecastMetricsDTO]:
        owned_run(self._runs, company_id, run_id)
        return [
            ForecastMetricsDTO.from_entity(m) for m in self._metrics.list_by_run(run_id)
        ]
