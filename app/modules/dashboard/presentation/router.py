"""Dashboard module — HTTP router."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.modules.dashboard.application.use_cases.erp_summary import GetErpSummary
from app.modules.dashboard.infrastructure.persistence.erp_summary import SqlErpSummaryReader
from app.shared.presentation.deps import get_db

from app.modules.dashboard.application.use_cases.dashboard import (
    AddWidget,
    GetDashboardSummary,
    RemoveWidget,
    ReorderWidgets,
    UpdateWidget,
)
from app.modules.dashboard.domain.repositories import DashboardWidgetRepository
from app.modules.dashboard.presentation.dependencies import get_dashboard_repository
from app.modules.dashboard.presentation.schemas import (
    AddWidgetRequest,
    DashboardChartResponse,
    DashboardOverviewResponse,
    DashboardWidgetResponse,
    ReorderWidgetsRequest,
    UpdateWidgetRequest,
)
from app.shared.presentation.deps import AuthenticatedUser, require_company_access
from app.shared.presentation.schemas import MessageResponse, PlaceholderResponse

router = APIRouter()


@router.get("/erp-summary")
def get_erp_summary(
    company_id: UUID,
    db: Annotated[Session, Depends(get_db, scope="function")],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> dict[str, Any]:
    """Sales, tickets, stock, purchases and lost sales — the ERP at a glance."""
    return GetErpSummary(SqlErpSummaryReader(db)).execute(company_id)


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    company_id: UUID,
    repo: Annotated[DashboardWidgetRepository, Depends(get_dashboard_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> DashboardOverviewResponse:
    use_case = GetDashboardSummary(repo)
    dto = use_case.execute(company_id=company_id)
    return DashboardOverviewResponse.model_validate(dto, from_attributes=True)


# --- Widget Management Endpoints ---

@router.post("/widgets", response_model=DashboardWidgetResponse, status_code=status.HTTP_201_CREATED)
def add_widget(
    company_id: UUID,
    request: AddWidgetRequest,
    repo: Annotated[DashboardWidgetRepository, Depends(get_dashboard_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> DashboardWidgetResponse:
    use_case = AddWidget(repo)
    dto = use_case.execute(
        company_id=company_id,
        title=request.title,
        widget_type=request.widget_type,
        position=request.position,
        config=request.config,
    )
    return DashboardWidgetResponse.model_validate(dto, from_attributes=True)


@router.put("/widgets/{widget_id}", response_model=DashboardWidgetResponse)
def update_widget(
    company_id: UUID,
    widget_id: UUID,
    request: UpdateWidgetRequest,
    repo: Annotated[DashboardWidgetRepository, Depends(get_dashboard_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> DashboardWidgetResponse:
    use_case = UpdateWidget(repo)
    dto = use_case.execute(
        company_id=company_id,
        widget_id=widget_id,
        title=request.title,
        config=request.config,
    )
    return DashboardWidgetResponse.model_validate(dto, from_attributes=True)


@router.delete("/widgets/{widget_id}", response_model=MessageResponse)
def remove_widget(
    company_id: UUID,
    widget_id: UUID,
    repo: Annotated[DashboardWidgetRepository, Depends(get_dashboard_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> MessageResponse:
    use_case = RemoveWidget(repo)
    use_case.execute(company_id=company_id, widget_id=widget_id)
    return MessageResponse(message="Widget deleted successfully")


@router.post("/widgets/reorder", response_model=MessageResponse)
def reorder_widgets(
    company_id: UUID,
    request: ReorderWidgetsRequest,
    repo: Annotated[DashboardWidgetRepository, Depends(get_dashboard_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> MessageResponse:
    use_case = ReorderWidgets(repo)
    use_case.execute(company_id=company_id, position_updates=request.positions)
    return MessageResponse(message="Widgets reordered successfully")


# --- Placeholder Endpoints ---

@router.get("/inventory", response_model=PlaceholderResponse)
def get_dashboard_inventory(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="dashboard", action="get_dashboard_inventory")

@router.get("/forecasting", response_model=PlaceholderResponse)
def get_dashboard_forecasting(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="dashboard", action="get_dashboard_forecasting")

@router.get("/kpis", response_model=PlaceholderResponse)
def get_dashboard_kpis(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="dashboard", action="get_dashboard_kpis")

@router.get("/recommendations", response_model=PlaceholderResponse)
def get_dashboard_recommendations(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="dashboard", action="get_dashboard_recommendations")

@router.get("/critical-products", response_model=PlaceholderResponse)
def get_dashboard_critical_products(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="dashboard", action="get_dashboard_critical_products")

@router.get("/recent-activity", response_model=PlaceholderResponse)
def get_dashboard_recent_activity(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="dashboard", action="get_dashboard_recent_activity")

@router.get("/charts/demand-vs-forecast", response_model=DashboardChartResponse)
def get_chart_demand_vs_forecast(company_id: UUID) -> DashboardChartResponse:
    return DashboardChartResponse(message="Endpoint scaffold ready", module="dashboard", action="get_chart_demand_vs_forecast")

@router.get("/charts/inventory-coverage", response_model=DashboardChartResponse)
def get_chart_inventory_coverage(company_id: UUID) -> DashboardChartResponse:
    return DashboardChartResponse(message="Endpoint scaffold ready", module="dashboard", action="get_chart_inventory_coverage")

@router.get("/charts/stockout-risk", response_model=DashboardChartResponse)
def get_chart_stockout_risk(company_id: UUID) -> DashboardChartResponse:
    return DashboardChartResponse(message="Endpoint scaffold ready", module="dashboard", action="get_chart_stockout_risk")

@router.get("/charts/replenishment-priority", response_model=DashboardChartResponse)
def get_chart_replenishment_priority(company_id: UUID) -> DashboardChartResponse:
    return DashboardChartResponse(message="Endpoint scaffold ready", module="dashboard", action="get_chart_replenishment_priority")
