"""Sales module — HTTP routers wired to use cases.

* `router` (/sales): legacy per-line sales CRUD, also used by imported history.
* `batches_router` (/sales/batches): import batches.
* `orders_router` (/sales-orders): the POS — tickets, catalog lookup, summary, void.
* `lost_sales_router` (/lost-sales): sale attempts blocked by missing stock.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.companies.domain.repositories import UserRepository
from app.modules.sales.application.dtos import (
    CatalogProductDTO,
    LostSaleDTO,
    SaleDTO,
    SalesBatchDTO,
    SalesOrderDTO,
    SalesOrderPageDTO,
    SalesSummaryDTO,
)
from app.modules.sales.application.use_cases.batch import (
    CreateSalesBatch,
    GetSalesBatch,
    ListSalesBatches,
)
from app.modules.sales.application.use_cases.order import (
    CreateSalesOrder,
    GetSalesOrder,
    GetSalesSummary,
    ListLostSales,
    ListSalesOrders,
    LookupProductByCode,
    RecordLostSale,
    SalesOrderReadModel,
    SearchCatalog,
    VoidSalesOrder,
)
from app.modules.sales.application.visibility import (
    order_for,
    order_page_for,
    sales_for,
    summary_for,
)
from app.modules.sales.application.use_cases.sale import (
    CreateSale,
    CreateSalesBulk,
    DeleteSale,
    GetSale,
    ListSales,
    ListSalesByProduct,
)
from app.modules.sales.domain.repositories import (
    InvoiceIssuer,
    LostSaleRepository,
    ProductCatalog,
    SaleRepository,
    SalesBatchRepository,
    SalesOrderRepository,
    StockLedger,
)
from app.modules.sales.presentation.dependencies import (
    get_invoice_issuer,
    get_lost_sale_repository,
    get_product_catalog,
    get_sale_repository,
    get_sales_batch_repository,
    get_sales_order_read_model,
    get_sales_order_repository,
    get_seller_directory,
    get_stock_ledger,
)
from app.modules.sales.presentation.schemas import (
    BulkSalesRequest,
    CreateSaleRequest,
    CreateSalesBatchRequest,
    CreateSalesOrderRequest,
    RecordLostSaleRequest,
    VoidSalesOrderRequest,
)
from app.modules.sales.infrastructure.persistence.history_import import import_sales_history
from app.shared.domain.errors import ForbiddenError
from app.shared.infrastructure.database import get_db
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
)
from app.shared.presentation.schemas import (
    MessageResponse,
    PaginationParams,
    PlaceholderResponse,
)

router = APIRouter()
batches_router = APIRouter()
orders_router = APIRouter()
lost_sales_router = APIRouter()


def _seller_name(users: UserRepository, current: AuthenticatedUser) -> str:
    user = users.get_by_id(current.user_id)
    if user is None:
        return ""
    return user.full_name or user.login


def _own_scope(current: AuthenticatedUser, requested: UUID | None) -> UUID | None:
    """Sellers only ever see their own tickets."""
    return current.user_id if current.role == "seller" else requested


# --- Sales -------------------------------------------------------------------
@router.get("", response_model=list[SaleDTO])
def list_sales(
    company_id: UUID,
    origin: Literal["pos", "imported"] | None = Query(
        None, description="pos = rung up in the app; imported = loaded from a spreadsheet"
    ),
    pagination: PaginationParams = Depends(get_pagination),
    current: AuthenticatedUser = Depends(require_company_access),
    repo: SaleRepository = Depends(get_sale_repository),
) -> list[SaleDTO]:
    sales = ListSales(repo).execute(
        company_id,
        offset=(pagination.page - 1) * pagination.size,
        limit=pagination.size,
        origin=origin,
    )
    return sales_for(current.role, sales)


@router.post("", response_model=SaleDTO, status_code=201)
def create_sale(
    company_id: UUID,
    request: CreateSaleRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SaleRepository = Depends(get_sale_repository),
) -> SaleDTO:
    return CreateSale(repo).execute(
        company_id,
        product_id=request.product_id,
        sale_date=request.sale_date,
        quantity=request.quantity,
        unit_price=request.unit_price,
        currency=request.currency,
        batch_id=request.batch_id,
    )


@router.post("/bulk", response_model=list[SaleDTO], status_code=201)
def create_sales_bulk(
    company_id: UUID,
    request: BulkSalesRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SaleRepository = Depends(get_sale_repository),
) -> list[SaleDTO]:
    items = [item.model_dump(mode="json") for item in request.items]
    return CreateSalesBulk(repo).execute(company_id, items=items)


class SalesImportRow(BaseModel):
    row: int | None = None
    code: str | None = None
    barcode: str | None = None
    name: str | None = None
    sale_date: str
    quantity: Decimal
    unit_price: Decimal | None = None
    seller_name: str | None = None
    # Ticket data: lines sharing a comprobante become one ticket.
    document_number: str | None = None
    payment_method: str | None = None
    client_name: str | None = None
    client_doc: str | None = None


class SalesImportRequest(BaseModel):
    rows: list[SalesImportRow] = Field(min_length=1, max_length=20000)
    allow_duplicates: bool = False
    # False = history (no stock movement); True = bulk sales that take stock out.
    affect_stock: bool = False


class SalesImportError(BaseModel):
    row: int
    message: str


class SalesImportResult(BaseModel):
    batch_id: UUID | None
    created: int
    tickets: int = 0
    units: int
    revenue: Decimal
    period_start: date | None
    period_end: date | None
    products: int
    errors: list[SalesImportError]


@router.post("/import", response_model=SalesImportResult, status_code=201)
def import_sales(
    company_id: UUID,
    request: SalesImportRequest,
    current: AuthenticatedUser = Depends(require_company_access),
    db: Session = Depends(get_db, scope="function"),
) -> SalesImportResult:
    """Load sales from a spreadsheet: as history, or as bulk sales that take stock out."""
    if current.role not in ("owner", "admin"):
        raise ForbiddenError(message="Solo el propietario o un administrador puede cargar ventas masivamente.")
    result = import_sales_history(
        db,
        company_id,
        [r.model_dump(mode="json") for r in request.rows],
        allow_duplicates=request.allow_duplicates,
        affect_stock=request.affect_stock,
    )
    return SalesImportResult(**result)


@router.get("/by-product/{product_id}", response_model=list[SaleDTO])
def get_sales_by_product(
    company_id: UUID,
    product_id: UUID,
    start: date,
    end: date,
    current: AuthenticatedUser = Depends(require_company_access),
    repo: SaleRepository = Depends(get_sale_repository),
) -> list[SaleDTO]:
    sales = ListSalesByProduct(repo).execute(company_id, product_id, start=start, end=end)
    return sales_for(current.role, sales)


@router.get("/summary", response_model=PlaceholderResponse)
def get_sales_summary(company_id: UUID) -> PlaceholderResponse:
    # Superseded by GET /sales-orders/summary (POS tickets).
    return PlaceholderResponse(
        message="Use /sales-orders/summary", module="sales", action="get_sales_summary"
    )


@router.get("/{sale_id}", response_model=SaleDTO)
def get_sale(
    company_id: UUID,
    sale_id: UUID,
    current: AuthenticatedUser = Depends(require_company_access),
    repo: SaleRepository = Depends(get_sale_repository),
) -> SaleDTO:
    return sales_for(current.role, [GetSale(repo).execute(company_id, sale_id)])[0]


@router.delete("/{sale_id}", response_model=MessageResponse)
def delete_sale(
    company_id: UUID,
    sale_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SaleRepository = Depends(get_sale_repository),
) -> MessageResponse:
    DeleteSale(repo).execute(company_id, sale_id)
    return MessageResponse(message="Sale deleted")


@router.patch("/{sale_id}", response_model=PlaceholderResponse)
def update_sale(company_id: UUID, sale_id: UUID) -> PlaceholderResponse:
    # TODO: SaleRepository has no update operation; revise the port if needed.
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="sales", action="update_sale"
    )


# --- Sales batches -----------------------------------------------------------
@batches_router.get("", response_model=list[SalesBatchDTO])
def list_sales_batches(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SalesBatchRepository = Depends(get_sales_batch_repository),
) -> list[SalesBatchDTO]:
    return ListSalesBatches(repo).execute(company_id)


@batches_router.post("", response_model=SalesBatchDTO, status_code=201)
def create_sales_batch(
    company_id: UUID,
    request: CreateSalesBatchRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SalesBatchRepository = Depends(get_sales_batch_repository),
) -> SalesBatchDTO:
    return CreateSalesBatch(repo).execute(
        company_id,
        source_file=request.source_file,
        period_start=request.period_start,
        period_end=request.period_end,
    )


@batches_router.get("/{batch_id}", response_model=SalesBatchDTO)
def get_sales_batch(
    company_id: UUID,
    batch_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SalesBatchRepository = Depends(get_sales_batch_repository),
) -> SalesBatchDTO:
    return GetSalesBatch(repo).execute(company_id, batch_id)


# --- POS: sales orders ---------------------------------------------------------
@orders_router.get("", response_model=SalesOrderPageDTO)
def list_sales_orders(
    company_id: UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    seller_id: UUID | None = None,
    document_type: Literal["boleta", "factura", "nota_venta"] | None = None,
    status: Literal["completed", "voided"] | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current: AuthenticatedUser = Depends(require_company_access),
    read: SalesOrderReadModel = Depends(get_sales_order_read_model),
) -> SalesOrderPageDTO:
    page_dto = ListSalesOrders(read).execute(
        company_id,
        date_from=date_from,
        date_to=date_to,
        seller_id=_own_scope(current, seller_id),
        document_type=document_type,
        status=status,
        q=q,
        page=page,
        size=size,
    )
    return order_page_for(current.role, page_dto)


@orders_router.post("", response_model=SalesOrderDTO, status_code=201)
def create_sales_order(
    company_id: UUID,
    request: CreateSalesOrderRequest,
    current: AuthenticatedUser = Depends(require_company_access),
    orders: SalesOrderRepository = Depends(get_sales_order_repository),
    catalog: ProductCatalog = Depends(get_product_catalog),
    stock: StockLedger = Depends(get_stock_ledger),
    issuer: InvoiceIssuer = Depends(get_invoice_issuer),
    read: SalesOrderReadModel = Depends(get_sales_order_read_model),
    users: UserRepository = Depends(get_seller_directory),
) -> SalesOrderDTO:
    order = CreateSalesOrder(orders, catalog, stock, issuer, read).execute(
        company_id,
        seller_id=current.user_id,
        seller_name=_seller_name(users, current),
        items=[item.model_dump(mode="json") for item in request.items],
        document_type=request.document_type,
        client_doc_type=request.client_doc_type,
        client_doc_number=request.client_doc_number,
        client_name=request.client_name,
        client_address=request.client_address,
        payment_method=request.payment_method,
        amount_received=request.amount_received,
        notes=request.notes,
    )
    return order_for(current.role, order)


@orders_router.get("/summary", response_model=SalesSummaryDTO)
def get_sales_orders_summary(
    company_id: UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    seller_id: UUID | None = None,
    current: AuthenticatedUser = Depends(require_company_access),
    read: SalesOrderReadModel = Depends(get_sales_order_read_model),
) -> SalesSummaryDTO:
    summary = GetSalesSummary(read).execute(
        company_id, date_from=date_from, date_to=date_to, seller_id=_own_scope(current, seller_id)
    )
    return summary_for(current.role, summary)


@orders_router.get("/lookup", response_model=CatalogProductDTO)
def lookup_product(
    company_id: UUID,
    code: str = Query(..., min_length=1, description="Barcode or SKU (exact, case-insensitive)"),
    _: AuthenticatedUser = Depends(require_company_access),
    catalog: ProductCatalog = Depends(get_product_catalog),
) -> CatalogProductDTO:
    return LookupProductByCode(catalog).execute(company_id, code)


@orders_router.get("/catalog", response_model=list[CatalogProductDTO])
def search_catalog(
    company_id: UUID,
    q: str = "",
    limit: int = Query(20, ge=1, le=200),
    _: AuthenticatedUser = Depends(require_company_access),
    catalog: ProductCatalog = Depends(get_product_catalog),
) -> list[CatalogProductDTO]:
    return SearchCatalog(catalog).execute(company_id, q, limit)


@orders_router.get("/{order_id}", response_model=SalesOrderDTO)
def get_sales_order(
    company_id: UUID,
    order_id: UUID,
    current: AuthenticatedUser = Depends(require_company_access),
    read: SalesOrderReadModel = Depends(get_sales_order_read_model),
) -> SalesOrderDTO:
    order = GetSalesOrder(read).execute(company_id, order_id, _own_scope(current, None))
    return order_for(current.role, order)


@orders_router.post("/{order_id}/void", response_model=SalesOrderDTO)
def void_sales_order(
    company_id: UUID,
    order_id: UUID,
    request: VoidSalesOrderRequest | None = None,
    current: AuthenticatedUser = Depends(require_company_access),
    orders: SalesOrderRepository = Depends(get_sales_order_repository),
    stock: StockLedger = Depends(get_stock_ledger),
    issuer: InvoiceIssuer = Depends(get_invoice_issuer),
    read: SalesOrderReadModel = Depends(get_sales_order_read_model),
    users: UserRepository = Depends(get_seller_directory),
) -> SalesOrderDTO:
    if current.role not in ("owner", "admin"):
        raise ForbiddenError(message="Solo el propietario o un administrador puede anular ventas.")
    return VoidSalesOrder(orders, stock, issuer, read).execute(
        company_id,
        order_id,
        voided_by=_seller_name(users, current),
        reason=request.reason if request else "",
    )


# --- Lost sales (quiebres) -------------------------------------------------------
@lost_sales_router.post("", response_model=LostSaleDTO, status_code=201)
def record_lost_sale(
    company_id: UUID,
    request: RecordLostSaleRequest,
    current: AuthenticatedUser = Depends(require_company_access),
    repo: LostSaleRepository = Depends(get_lost_sale_repository),
    catalog: ProductCatalog = Depends(get_product_catalog),
    users: UserRepository = Depends(get_seller_directory),
) -> LostSaleDTO:
    return RecordLostSale(repo, catalog).execute(
        company_id,
        product_id=request.product_id,
        requested_quantity=request.requested_quantity,
        available_quantity=request.available_quantity,
        seller_id=current.user_id,
        seller_name=_seller_name(users, current),
        source=request.source,
    )


@lost_sales_router.get("", response_model=list[LostSaleDTO])
def list_lost_sales(
    company_id: UUID,
    product_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    _: AuthenticatedUser = Depends(require_company_access),
    read: SalesOrderReadModel = Depends(get_sales_order_read_model),
) -> list[LostSaleDTO]:
    return ListLostSales(read).execute(
        company_id, product_id=product_id, date_from=date_from, date_to=date_to
    )
