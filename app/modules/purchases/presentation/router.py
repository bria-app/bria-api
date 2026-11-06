"""Purchases module — HTTP router wired to use cases."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.purchases.application.dtos import (
    PurchaseBatchResultDTO,
    PurchaseCatalogItemDTO,
    PurchaseDocumentDetailDTO,
    PurchaseDocumentPageDTO,
    PurchaseDTO,
    PurchaseImportResultDTO,
    PurchaseLineDTO,
)
from app.modules.purchases.application.use_cases.purchase import (
    CreatePurchase,
    GetPurchaseCatalog,
    GetPurchaseDocument,
    ImportPurchases,
    ListPurchaseDocuments,
    ListPurchases,
    RegisterPurchaseDocument,
)
from app.modules.purchases.infrastructure.persistence.receiving import SqlInboundStockGateway
from app.modules.purchases.infrastructure.persistence.repositories import SqlPurchaseRepository
from app.modules.purchases.presentation.dependencies import (
    get_inbound_stock_gateway,
    get_purchase_repository,
)
from app.modules.purchases.presentation.schemas import (
    CreatePurchaseRequest,
    PurchaseBatchRequest,
    PurchaseImportRequest,
)
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
)
from app.shared.presentation.schemas import PaginationParams

router = APIRouter()


@router.get("", response_model=list[PurchaseLineDTO])
def list_purchases(
    company_id: UUID,
    supplier_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    pagination: PaginationParams = Depends(get_pagination),
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlPurchaseRepository = Depends(get_purchase_repository),
) -> list[PurchaseLineDTO]:
    return ListPurchases(repo).execute(
        company_id,
        supplier_id=supplier_id,
        date_from=date_from,
        date_to=date_to,
        offset=(pagination.page - 1) * pagination.size,
        limit=pagination.size,
    )


@router.post("", response_model=PurchaseDTO, status_code=201)
def create_purchase(
    company_id: UUID,
    request: CreatePurchaseRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlPurchaseRepository = Depends(get_purchase_repository),
    stock: SqlInboundStockGateway = Depends(get_inbound_stock_gateway),
) -> PurchaseDTO:
    return CreatePurchase(repo, stock).execute(company_id, **request.model_dump())


@router.get("/catalog", response_model=list[PurchaseCatalogItemDTO])
def purchase_catalog(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    stock: SqlInboundStockGateway = Depends(get_inbound_stock_gateway),
) -> list[PurchaseCatalogItemDTO]:
    return GetPurchaseCatalog(stock).execute(company_id)


@router.post("/batch", response_model=PurchaseBatchResultDTO, status_code=201)
def register_purchase_document(
    company_id: UUID,
    request: PurchaseBatchRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlPurchaseRepository = Depends(get_purchase_repository),
    stock: SqlInboundStockGateway = Depends(get_inbound_stock_gateway),
) -> PurchaseBatchResultDTO:
    return RegisterPurchaseDocument(repo, stock).execute(
        company_id,
        supplier_id=request.supplier_id,
        purchase_date=request.purchase_date,
        document_number=request.document_number,
        notes=request.notes,
        costs_include_igv=request.costs_include_igv,
        items=[i.model_dump() for i in request.items],
    )


@router.post("/import", response_model=PurchaseImportResultDTO)
def import_purchases(
    company_id: UUID,
    request: PurchaseImportRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlPurchaseRepository = Depends(get_purchase_repository),
    stock: SqlInboundStockGateway = Depends(get_inbound_stock_gateway),
) -> PurchaseImportResultDTO:
    payload = request.model_dump()
    rows = payload.pop("rows")
    return ImportPurchases(repo, stock).execute(company_id, rows=rows, **payload)


@router.get("/documents", response_model=PurchaseDocumentPageDTO)
def list_purchase_documents(
    company_id: UUID,
    supplier_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    q: str | None = Query(None, max_length=100),
    pagination: PaginationParams = Depends(get_pagination),
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlPurchaseRepository = Depends(get_purchase_repository),
) -> PurchaseDocumentPageDTO:
    return ListPurchaseDocuments(repo).execute(
        company_id,
        supplier_id=supplier_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
        page=pagination.page,
        size=pagination.size,
    )


@router.get("/documents/{document_id}", response_model=PurchaseDocumentDetailDTO)
def get_purchase_document(
    company_id: UUID,
    document_id: str,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlPurchaseRepository = Depends(get_purchase_repository),
) -> PurchaseDocumentDetailDTO:
    return GetPurchaseDocument(repo).execute(company_id, document_id)
