"""Reports module — HTTP router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from app.modules.files.presentation.dependencies import get_storage_port
from app.modules.forecasting.infrastructure.persistence.repositories import (
    SqlForecastMetricsRepository,
    SqlForecastRunRepository,
)
from app.modules.forecasting.presentation.dependencies import (
    get_metrics_repository,
    get_run_repository,
)
from app.modules.kpis.infrastructure.persistence.repositories import SqlKpiRepository
from app.modules.kpis.presentation.dependencies import get_kpi_repository
from app.modules.products.infrastructure.persistence.repositories import (
    SqlProductRepository,
)
from app.modules.products.presentation.dependencies import get_product_repository
from app.modules.recommendations.infrastructure.persistence.repositories import (
    SqlRecommendationRepository,
)
from app.modules.recommendations.presentation.dependencies import (
    get_recommendation_repository,
)
from app.modules.reports.application.use_cases.report import (
    CreateReport,
    DownloadReport,
    GenerateReport,
    GetReport,
    ListReports,
)
from app.modules.reports.domain.repositories import ReportRepository
from app.modules.reports.presentation.dependencies import get_report_repository
from app.modules.reports.presentation.schemas import (
    CreateReportRequest,
    ReportResponse,
    ReportStatusResponse,
    ReportTemplateResponse,
)
from app.shared.application.ports import StoragePort
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
)
from app.shared.presentation.schemas import (
    PaginatedResponse,
    PaginationParams,
    PlaceholderResponse,
)

router = APIRouter()


@router.get("/health", response_model=PlaceholderResponse)
def health_check(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="reports", action="health_check"
    )


@router.get("", response_model=PaginatedResponse[ReportResponse])
def list_reports(
    company_id: UUID,
    repo: Annotated[ReportRepository, Depends(get_report_repository)],
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> PaginatedResponse[ReportResponse]:
    use_case = ListReports(repo)
    offset = (pagination.page - 1) * pagination.size
    dtos = use_case.execute(
        company_id=company_id,
        offset=offset,
        limit=pagination.size,
    )
    return PaginatedResponse(
        items=[ReportResponse.model_validate(d) for d in dtos],
        total=len(dtos),
        page=pagination.page,
        size=pagination.size,
        pages=1,
    )


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    company_id: UUID,
    request: CreateReportRequest,
    repo: Annotated[ReportRepository, Depends(get_report_repository)],
    storage: Annotated[StoragePort, Depends(get_storage_port)],
    runs: Annotated[SqlForecastRunRepository, Depends(get_run_repository)],
    metrics: Annotated[SqlForecastMetricsRepository, Depends(get_metrics_repository)],
    kpis: Annotated[SqlKpiRepository, Depends(get_kpi_repository)],
    recommendations: Annotated[
        SqlRecommendationRepository, Depends(get_recommendation_repository)
    ],
    products: Annotated[SqlProductRepository, Depends(get_product_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> ReportResponse:
    # 1. Create it in pending state
    create_use_case = CreateReport(repo)
    dto = create_use_case.execute(
        company_id=company_id,
        title=request.title,
        report_type=request.report_type,
        params=request.params,
    )

    # 2. Synchronously generate it with real DSS content.
    generate_use_case = GenerateReport(
        repo,
        storage,
        runs=runs,
        metrics=metrics,
        kpis=kpis,
        recommendations=recommendations,
        products=products,
    )
    ready_dto = generate_use_case.execute(company_id=company_id, report_id=dto.id)

    return ReportResponse.model_validate(ready_dto)


@router.get("/templates", response_model=PlaceholderResponse)
def list_templates(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="reports", action="list_templates"
    )


@router.get("/templates/{template_id}", response_model=ReportTemplateResponse)
def get_template(company_id: UUID, template_id: str) -> ReportTemplateResponse:
    return ReportTemplateResponse(
        message="Endpoint scaffold ready", module="reports", action="get_template"
    )


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    company_id: UUID,
    report_id: UUID,
    repo: Annotated[ReportRepository, Depends(get_report_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> ReportResponse:
    use_case = GetReport(repo)
    dto = use_case.execute(company_id=company_id, report_id=report_id)
    return ReportResponse.model_validate(dto)


@router.delete("/{report_id}", response_model=PlaceholderResponse)
def delete_report(company_id: UUID, report_id: UUID) -> PlaceholderResponse:
    # No DeleteReport usecase requested natively, just leaving as placeholder
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="reports", action="delete_report"
    )


@router.get("/{report_id}/status", response_model=ReportStatusResponse)
def get_report_status(company_id: UUID, report_id: UUID) -> ReportStatusResponse:
    return ReportStatusResponse(
        message="Endpoint scaffold ready", module="reports", action="get_report_status"
    )


@router.get("/{report_id}/download")
def download_report(
    company_id: UUID,
    report_id: UUID,
    repo: Annotated[ReportRepository, Depends(get_report_repository)],
    storage: Annotated[StoragePort, Depends(get_storage_port)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> Response:
    use_case = DownloadReport(repo, storage)
    content, file_name, content_type = use_case.execute(
        company_id=company_id, report_id=report_id
    )
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/{report_id}/preview", response_model=PlaceholderResponse)
def preview_report(company_id: UUID, report_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="reports", action="preview_report"
    )


@router.post("/{report_id}/regenerate", response_model=ReportResponse)
def regenerate_report(
    company_id: UUID,
    report_id: UUID,
    repo: Annotated[ReportRepository, Depends(get_report_repository)],
    storage: Annotated[StoragePort, Depends(get_storage_port)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> ReportResponse:
    # We can wire this directly to GenerateReport to re-run it
    use_case = GenerateReport(repo, storage)
    dto = use_case.execute(company_id=company_id, report_id=report_id)
    return ReportResponse.model_validate(dto)


@router.post("/{report_id}/send-email", response_model=PlaceholderResponse)
def send_report_email(company_id: UUID, report_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="reports", action="send_report_email"
    )

# The other placeholders
@router.post("/forecast", response_model=PlaceholderResponse)
def create_forecast_report(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="reports", action="create_forecast_report")

@router.post("/kpis", response_model=PlaceholderResponse)
def create_kpis_report(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="reports", action="create_kpis_report")

@router.post("/recommendations", response_model=PlaceholderResponse)
def create_recommendations_report(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="reports", action="create_recommendations_report")

@router.post("/inventory", response_model=PlaceholderResponse)
def create_inventory_report(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="reports", action="create_inventory_report")

@router.post("/executive-summary", response_model=PlaceholderResponse)
def create_executive_summary_report(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="reports", action="create_executive_summary_report")
