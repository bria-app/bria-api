"""KPIs module — HTTP router wired to use cases.

Implemented: record a KPI, list company KPIs, list product KPIs. Automatic KPI
computation (calculate) is a cross-module orchestration left as a placeholder.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.kpis.application.dtos import KpiDTO
from app.modules.forecasting.domain.repositories import (
    ForecastResultRepository,
    ForecastRunRepository,
)
from app.modules.inventory.domain.repositories import InventoryMovementRepository
from app.modules.kpis.application.use_cases.compute import ComputeCompanyKpis
from app.modules.kpis.application.use_cases.kpi import (
    ListKpis,
    ListProductKpis,
    RecordKpi,
)
from app.modules.kpis.domain.repositories import KpiRepository
from app.modules.kpis.presentation.dependencies import (
    get_kpi_repository,
    get_movement_repository,
    get_product_repository,
    get_result_repository,
    get_run_repository,
    parse_kpi_type,
)
from app.modules.kpis.presentation.schemas import RecordKpiRequest
from app.modules.products.domain.repositories import ProductRepository
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
)
from app.shared.presentation.schemas import PaginationParams

router = APIRouter()


@router.get("", response_model=list[KpiDTO])
def list_kpis(
    company_id: UUID,
    pagination: PaginationParams = Depends(get_pagination),
    _: AuthenticatedUser = Depends(require_company_access),
    repo: KpiRepository = Depends(get_kpi_repository),
) -> list[KpiDTO]:
    return ListKpis(repo).execute(
        company_id,
        offset=(pagination.page - 1) * pagination.size,
        limit=pagination.size,
    )


@router.post("", response_model=KpiDTO, status_code=201)
def record_kpi(
    company_id: UUID,
    request: RecordKpiRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: KpiRepository = Depends(get_kpi_repository),
) -> KpiDTO:
    return RecordKpi(repo).execute(
        company_id,
        product_id=request.product_id,
        kpi_type=parse_kpi_type(request.kpi_type),
        value=request.value,
        run_id=request.run_id,
        computed_at=request.computed_at,
    )


@router.post("/calculate", response_model=list[KpiDTO], status_code=201)
def calculate_kpis(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    kpis: KpiRepository = Depends(get_kpi_repository),
    products: ProductRepository = Depends(get_product_repository),
    runs: ForecastRunRepository = Depends(get_run_repository),
    results: ForecastResultRepository = Depends(get_result_repository),
    movements: InventoryMovementRepository = Depends(get_movement_repository),
) -> list[KpiDTO]:
    return ComputeCompanyKpis(
        products=products,
        runs=runs,
        results=results,
        movements=movements,
        kpis=kpis,
    ).execute(company_id)


@router.get("/by-product/{product_id}", response_model=list[KpiDTO])
def list_product_kpis(
    company_id: UUID,
    product_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: KpiRepository = Depends(get_kpi_repository),
) -> list[KpiDTO]:
    return ListProductKpis(repo).execute(company_id, product_id)
