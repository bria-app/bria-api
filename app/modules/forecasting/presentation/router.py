"""Forecasting module — HTTP routers wired to use cases.

Run lifecycle: preview a scope, create a run (ERP scope -> dataset built from sales and the
background job started in the same call; legacy CSV dataset path kept), poll status,
cancel, read results/metrics, and the read models over finished runs (overview,
forecast-vs-actual tracking, runs per product, product insight charts).

Static paths are declared before ``/{run_id}`` so they are not captured by it.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.modules.data_preparation.domain.repositories import PreparedDatasetRepository
from app.modules.data_preparation.infrastructure.erp_source import ErpDataSource
from app.modules.forecasting.application.dtos import (
    ForecastMetricsDTO,
    ForecastResultDTO,
    ForecastRunDTO,
)
from app.modules.forecasting.application.use_cases.insights import (
    GetRunOverview,
    ListProductRuns,
    TrackForecastRun,
)
from app.modules.forecasting.application.use_cases.run import (
    CancelForecastRun,
    CreateForecastRun,
    GetForecastRun,
    ListForecastRuns,
    ListRunMetrics,
    ListRunResults,
)
from app.modules.forecasting.application.use_cases.scoped import (
    CreateScopedForecastRun,
    GetProductInsight,
    PreviewForecastScope,
    enforce_plan,
)
from app.modules.forecasting.domain.exceptions import ForecastRunNotFoundError
from app.modules.forecasting.domain.repositories import (
    ForecastMetricsRepository,
    ForecastResultRepository,
    ForecastRunRepository,
)
from app.modules.forecasting.infrastructure.background import run_forecast_job
from app.modules.forecasting.infrastructure.plan import FREE_MONTHLY_RUNS, company_is_premium, runs_used_this_month
from app.modules.forecasting.presentation.dependencies import (
    get_dataset_repository,
    get_erp_source,
    get_metrics_repository,
    get_recommendation_repository,
    get_result_repository,
    get_run_repository,
    get_session,
)
from app.modules.forecasting.presentation.schemas import (
    CreateForecastRunRequest,
    ScopePreviewRequest,
)
from app.modules.recommendations.domain.repositories import RecommendationRepository
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
)
from app.shared.presentation.schemas import PaginationParams, PlaceholderResponse

runs_router = APIRouter()
forecasts_router = APIRouter()


@runs_router.post("/scope-preview")
def preview_scope(
    company_id: UUID,
    request: ScopePreviewRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    source: ErpDataSource = Depends(get_erp_source),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return PreviewForecastScope(source, lambda cid: company_is_premium(session, cid)).execute(
        company_id, request.scope.as_dict(), request.frequency, request.as_of
    )


@runs_router.post("", response_model=ForecastRunDTO, status_code=201)
def create_run(
    company_id: UUID,
    request: CreateForecastRunRequest,
    background_tasks: BackgroundTasks,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
    datasets: PreparedDatasetRepository = Depends(get_dataset_repository),
    source: ErpDataSource = Depends(get_erp_source),
    session: Session = Depends(get_session),
) -> ForecastRunDTO:
    if request.scope is None:
        # Legacy: run over a prepared (CSV) dataset; the client calls /execute. It counts
        # against the same monthly quota as the ERP-scoped runs (audit M-14).
        enforce_plan(
            company_is_premium(session, company_id),
            runs_used_this_month(session, company_id),
            FREE_MONTHLY_RUNS,
        )
        return CreateForecastRun(repo, datasets).execute(
            company_id,
            model_name=request.model_name,
            horizon_days=request.horizon_days,
            dataset_id=request.dataset_id,
        )
    is_premium = lambda cid: company_is_premium(session, cid)  # noqa: E731
    run = CreateScopedForecastRun(
        repo,
        datasets,
        PreviewForecastScope(source, is_premium),
        is_premium,
        lambda cid: runs_used_this_month(session, cid),
        FREE_MONTHLY_RUNS,
    ).execute(
        company_id,
        scope=request.scope.as_dict(),
        horizon_days=request.horizon_days,
        frequency=request.frequency,
        model_name=request.model_name,
        as_of=request.as_of,
    )
    # The request session commits before the response (scope="function"), so the job
    # always finds the run.
    background_tasks.add_task(run_forecast_job, run.id)
    return run


@runs_router.get("/quota")
def get_forecast_quota(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """How many predictions the plan still allows this month (null limit = unlimited)."""
    premium = company_is_premium(session, company_id)
    used = runs_used_this_month(session, company_id)
    limit = None if premium else FREE_MONTHLY_RUNS
    return {
        "plan": "premium" if premium else "free",
        "monthly_limit": limit,
        "used": used,
        "remaining": None if limit is None else max(0, limit - used),
    }


@runs_router.get("", response_model=list[ForecastRunDTO])
def list_runs(
    company_id: UUID,
    pagination: PaginationParams = Depends(get_pagination),
    is_backtest: bool | None = Query(
        None,
        description="true: only tests against the past; false: only real forecasts; "
        "omitted: every run.",
    ),
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
) -> list[ForecastRunDTO]:
    return ListForecastRuns(repo).execute(
        company_id,
        offset=(pagination.page - 1) * pagination.size,
        limit=pagination.size,
        is_backtest=is_backtest,
    )


@runs_router.get("/by-product/{product_id}")
def list_product_runs(
    company_id: UUID,
    product_id: UUID,
    limit: int = Query(10, ge=1, le=50),
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
    results: ForecastResultRepository = Depends(get_result_repository),
    source: ErpDataSource = Depends(get_erp_source),
) -> list[dict[str, Any]]:
    tracking = TrackForecastRun(repo, results, source)
    return ListProductRuns(repo, tracking, source).execute(company_id, product_id, limit)


@runs_router.get("/product-insight/{product_id}")
def get_product_insight(
    company_id: UUID,
    product_id: UUID,
    frequency: str = Query("weekly"),
    periods: int = Query(52, ge=4, le=156),
    _: AuthenticatedUser = Depends(require_company_access),
    source: ErpDataSource = Depends(get_erp_source),
) -> dict[str, Any]:
    return GetProductInsight(source).execute(company_id, product_id, frequency, periods)


@runs_router.post("/compare-models", response_model=PlaceholderResponse)
def compare_models(company_id: UUID) -> PlaceholderResponse:
    # TODO: run FTGM vs baseline and compare metrics (the engine already reports the
    # rolling-origin skill vs seasonal naive per product in the run diagnostics).
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="forecasting", action="compare_models"
    )


@runs_router.post("/{run_id}/execute", response_model=ForecastRunDTO, status_code=202)
def execute_run(
    company_id: UUID,
    run_id: UUID,
    background_tasks: BackgroundTasks,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
) -> ForecastRunDTO:
    run = GetForecastRun(repo).execute(company_id, run_id)  # 404 if missing / other company
    # Scoped runs already started their job on creation; don't run them twice.
    if run.status == "pending" and not run.scope:
        background_tasks.add_task(run_forecast_job, run_id)
    return run


@runs_router.post("/{run_id}/cancel", response_model=ForecastRunDTO)
def cancel_run(
    company_id: UUID,
    run_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
) -> ForecastRunDTO:
    return CancelForecastRun(repo).execute(company_id, run_id)


@runs_router.get("/{run_id}/status", response_model=ForecastRunDTO)
def get_run_status(
    company_id: UUID,
    run_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
) -> ForecastRunDTO:
    return GetForecastRun(repo).execute(company_id, run_id)


@runs_router.get("/{run_id}/results", response_model=list[ForecastResultDTO])
def get_run_results(
    company_id: UUID,
    run_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastResultRepository = Depends(get_result_repository),
    runs: ForecastRunRepository = Depends(get_run_repository),
) -> list[ForecastResultDTO]:
    return ListRunResults(repo, runs).execute(company_id, run_id)


@runs_router.get("/{run_id}/metrics", response_model=list[ForecastMetricsDTO])
def get_run_metrics(
    company_id: UUID,
    run_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastMetricsRepository = Depends(get_metrics_repository),
    runs: ForecastRunRepository = Depends(get_run_repository),
) -> list[ForecastMetricsDTO]:
    return ListRunMetrics(repo, runs).execute(company_id, run_id)


@runs_router.get("/{run_id}/tracking")
def get_run_tracking(
    company_id: UUID,
    run_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
    results: ForecastResultRepository = Depends(get_result_repository),
    source: ErpDataSource = Depends(get_erp_source),
) -> dict[str, Any]:
    return TrackForecastRun(repo, results, source).execute(company_id, run_id)


@runs_router.get("/{run_id}/overview")
def get_run_overview(
    company_id: UUID,
    run_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
    results: ForecastResultRepository = Depends(get_result_repository),
    metrics: ForecastMetricsRepository = Depends(get_metrics_repository),
    recommendations: RecommendationRepository = Depends(get_recommendation_repository),
    source: ErpDataSource = Depends(get_erp_source),
) -> dict[str, Any]:
    return GetRunOverview(repo, results, metrics, recommendations, source).execute(company_id, run_id)


@runs_router.get("/{run_id}", response_model=ForecastRunDTO)
def get_run(
    company_id: UUID,
    run_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
) -> ForecastRunDTO:
    return GetForecastRun(repo).execute(company_id, run_id)


# --- Forecast results convenience endpoints ----------------------------------
@forecasts_router.get("/latest", response_model=ForecastRunDTO)
def get_latest_run(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ForecastRunRepository = Depends(get_run_repository),
) -> ForecastRunDTO:
    latest = repo.get_latest_by_company(company_id)
    if latest is None:
        raise ForecastRunNotFoundError(message="Aún no tienes pronósticos. Crea uno desde Pronósticos.")
    return ForecastRunDTO.from_entity(latest)
