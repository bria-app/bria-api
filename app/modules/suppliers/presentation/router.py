"""Suppliers module — HTTP router wired to use cases."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.suppliers.application.dtos import (
    SupplierDTO,
    SupplierImportResultDTO,
    SupplierSummaryDTO,
)
from app.modules.suppliers.application.use_cases.supplier import (
    CreateSupplier,
    DeleteSupplier,
    GetSupplier,
    GetSupplierSummary,
    ImportSuppliers,
    ListSuppliers,
    UpdateSupplier,
)
from app.modules.suppliers.infrastructure.persistence.queries import SqlSupplierStatsReader
from app.modules.suppliers.infrastructure.persistence.repositories import SqlSupplierRepository
from app.modules.suppliers.presentation.dependencies import (
    get_supplier_repository,
    get_supplier_stats_reader,
)
from app.modules.suppliers.presentation.schemas import (
    CreateSupplierRequest,
    ImportSuppliersRequest,
    UpdateSupplierRequest,
)
from app.shared.presentation.deps import AuthenticatedUser, require_company_access
from app.shared.presentation.schemas import MessageResponse

router = APIRouter()


@router.get("", response_model=list[SupplierDTO])
def list_suppliers(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlSupplierRepository = Depends(get_supplier_repository),
    stats: SqlSupplierStatsReader = Depends(get_supplier_stats_reader),
) -> list[SupplierDTO]:
    return ListSuppliers(repo, stats).execute(company_id)


@router.post("", response_model=SupplierDTO, status_code=201)
def create_supplier(
    company_id: UUID,
    request: CreateSupplierRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlSupplierRepository = Depends(get_supplier_repository),
) -> SupplierDTO:
    return CreateSupplier(repo).execute(company_id, **request.model_dump())


@router.post("/import", response_model=SupplierImportResultDTO)
def import_suppliers(
    company_id: UUID,
    request: ImportSuppliersRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlSupplierRepository = Depends(get_supplier_repository),
) -> SupplierImportResultDTO:
    return ImportSuppliers(repo, repo).execute(company_id, [r.model_dump() for r in request.rows])


@router.get("/{supplier_id}", response_model=SupplierDTO)
def get_supplier(
    company_id: UUID,
    supplier_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlSupplierRepository = Depends(get_supplier_repository),
) -> SupplierDTO:
    return GetSupplier(repo).execute(company_id, supplier_id)


@router.get("/{supplier_id}/summary", response_model=SupplierSummaryDTO)
def get_supplier_summary(
    company_id: UUID,
    supplier_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlSupplierRepository = Depends(get_supplier_repository),
    stats: SqlSupplierStatsReader = Depends(get_supplier_stats_reader),
) -> SupplierSummaryDTO:
    return GetSupplierSummary(repo, stats).execute(company_id, supplier_id)


@router.patch("/{supplier_id}", response_model=SupplierDTO)
def update_supplier(
    company_id: UUID,
    supplier_id: UUID,
    request: UpdateSupplierRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlSupplierRepository = Depends(get_supplier_repository),
) -> SupplierDTO:
    return UpdateSupplier(repo).execute(company_id, supplier_id, **request.model_dump())


@router.delete("/{supplier_id}", response_model=MessageResponse)
def delete_supplier(
    company_id: UUID,
    supplier_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlSupplierRepository = Depends(get_supplier_repository),
) -> MessageResponse:
    DeleteSupplier(repo).execute(company_id, supplier_id)
    return MessageResponse(message="Proveedor eliminado")
