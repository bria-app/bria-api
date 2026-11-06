"""Inventory module — HTTP router wired to use cases.

Implemented: derived current stock, movement create/list/get, snapshot create/list,
replenishment create/list/update-status, stockout create/list-open/close. Endpoints
whose domain ports do not exist yet (bulk, movement update/delete, get-by-id for
snapshots, automatic stockout detection, company-wide current stock) remain placeholders.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.inventory.application.dtos import (
    AdjustmentResultDTO,
    InventoryOverviewDTO,
    InventoryValuationDTO,
    MovementDTO,
    ReplenishmentDTO,
    SnapshotDTO,
    StockLevelDTO,
    StockoutDTO,
)
from app.modules.inventory.application.use_cases.movement import (
    CreateMovement,
    GetCompanyStockLevels,
    GetCurrentStock,
    GetMovement,
    ListMovements,
)
from app.modules.inventory.application.use_cases.detection import DetectStockouts
from app.modules.inventory.application.visibility import (
    movement_for,
    movements_for,
    overview_for,
    valuation_for,
)
from app.modules.inventory.application.use_cases.stock_records import (
    CloseStockout,
    CreateReplenishment,
    CreateSnapshot,
    CreateStockout,
    ListOpenStockouts,
    ListProductSnapshots,
    ListReplenishments,
    UpdateReplenishmentStatus,
)
from app.modules.inventory.domain.repositories import (
    InventoryMovementRepository,
    ReplenishmentRepository,
    StockoutEventRepository,
    StockSnapshotRepository,
)
from app.modules.inventory.application.use_cases.adjustment import AdjustStock
from app.modules.inventory.domain.enums import AdjustmentMode, AdjustmentReason
from app.modules.inventory.infrastructure.adapters.costing import (
    SqlInboundCosting,
    SqlStockReader,
)
from app.modules.inventory.infrastructure.persistence.overview import SqlInventoryOverviewQuery
from app.modules.inventory.presentation.schemas import StockAdjustmentRequest
from app.modules.inventory.presentation.dependencies import (
    get_inbound_costing,
    get_overview_query,
    get_stock_reader,
    get_movement_repository,
    get_product_repository,
    get_replenishment_repository,
    get_snapshot_repository,
    get_stockout_repository,
    parse_movement_type,
    parse_replenishment_status,
)
from app.modules.products.domain.repositories import ProductRepository
from app.modules.inventory.presentation.schemas import (
    CloseStockoutRequest,
    CreateMovementRequest,
    CreateReplenishmentRequest,
    CreateSnapshotRequest,
    CreateStockoutRequest,
    UpdateReplenishmentRequest,
)
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
)
from app.shared.presentation.schemas import (
    MessageResponse,
    PaginationParams,
)

router = APIRouter()


# --- Overview, valuation, adjustments -----------------------------------------
@router.get("/overview", response_model=InventoryOverviewDTO)
def get_inventory_overview(
    company_id: UUID,
    include_inactive: bool = False,
    current: AuthenticatedUser = Depends(require_company_access),
    query: SqlInventoryOverviewQuery = Depends(get_overview_query),
) -> InventoryOverviewDTO:
    """Main inventory table: every product with stock, value, status, coverage and sales."""
    return overview_for(current.role, query.overview(company_id, include_inactive=include_inactive))


@router.get("/valuation", response_model=InventoryValuationDTO)
def get_inventory_valuation(
    company_id: UUID,
    current: AuthenticatedUser = Depends(require_company_access),
    query: SqlInventoryOverviewQuery = Depends(get_overview_query),
) -> InventoryValuationDTO:
    return valuation_for(current.role, query.valuation(company_id))


@router.post("/adjustments", response_model=AdjustmentResultDTO, status_code=201)
def create_adjustment(
    company_id: UUID,
    request: StockAdjustmentRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    products: ProductRepository = Depends(get_product_repository),
    movements: InventoryMovementRepository = Depends(get_movement_repository),
    stock: SqlStockReader = Depends(get_stock_reader),
) -> AdjustmentResultDTO:
    return AdjustStock(products=products, movements=movements, stock=stock).execute(
        company_id,
        product_id=request.product_id,
        mode=AdjustmentMode(request.mode),
        quantity=request.quantity,
        reason=AdjustmentReason(request.reason),
        note=request.note,
    )


# --- Current stock (derived) -------------------------------------------------
@router.get("/current-stock/{product_id}", response_model=StockLevelDTO)
def get_current_stock_by_product(
    company_id: UUID,
    product_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: InventoryMovementRepository = Depends(get_movement_repository),
    products: ProductRepository = Depends(get_product_repository),
) -> StockLevelDTO:
    return GetCurrentStock(repo, products).execute(company_id, product_id)


@router.get("/current-stock", response_model=list[StockLevelDTO])
def get_company_stock_levels(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    movements: InventoryMovementRepository = Depends(get_movement_repository),
    products: ProductRepository = Depends(get_product_repository),
) -> list[StockLevelDTO]:
    """Current on-hand stock for every active product (derived from the ledger)."""
    return GetCompanyStockLevels(products=products, movements=movements).execute(company_id)


# --- Movements ---------------------------------------------------------------
@router.get("/movements", response_model=list[MovementDTO])
def list_movements(
    company_id: UUID,
    reference_type: str | None = Query(
        None,
        max_length=20,
        description='Only movements of this origin, e.g. "sale", "sale_void", "purchase", "adjustment"',
    ),
    pagination: PaginationParams = Depends(get_pagination),
    current: AuthenticatedUser = Depends(require_company_access),
    repo: InventoryMovementRepository = Depends(get_movement_repository),
) -> list[MovementDTO]:
    """Newest first, one page at a time (page/size)."""
    movements = ListMovements(repo).execute(
        company_id,
        offset=(pagination.page - 1) * pagination.size,
        limit=pagination.size,
        reference_type=reference_type,
    )
    return movements_for(current.role, movements)


@router.post("/movements", response_model=MovementDTO, status_code=201)
def create_movement(
    company_id: UUID,
    request: CreateMovementRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: InventoryMovementRepository = Depends(get_movement_repository),
    costing: SqlInboundCosting = Depends(get_inbound_costing),
) -> MovementDTO:
    return CreateMovement(repo, costing).execute(
        company_id,
        product_id=request.product_id,
        movement_type=parse_movement_type(request.movement_type),
        quantity=request.quantity,
        reason=request.reason,
        occurred_at=request.occurred_at,
        unit_cost=request.unit_cost,
        reference_type=request.reference_type,
        reference_id=request.reference_id,
    )


@router.get("/movements/{movement_id}", response_model=MovementDTO)
def get_movement(
    company_id: UUID,
    movement_id: UUID,
    current: AuthenticatedUser = Depends(require_company_access),
    repo: InventoryMovementRepository = Depends(get_movement_repository),
) -> MovementDTO:
    return movement_for(current.role, GetMovement(repo).execute(company_id, movement_id))


# --- Snapshots ---------------------------------------------------------------
@router.post("/snapshots", response_model=SnapshotDTO, status_code=201)
def create_snapshot(
    company_id: UUID,
    request: CreateSnapshotRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: StockSnapshotRepository = Depends(get_snapshot_repository),
) -> SnapshotDTO:
    return CreateSnapshot(repo).execute(
        company_id,
        product_id=request.product_id,
        quantity_on_hand=request.quantity_on_hand,
        snapshot_at=request.snapshot_at,
    )


@router.get("/snapshots/by-product/{product_id}", response_model=list[SnapshotDTO])
def list_product_snapshots(
    company_id: UUID,
    product_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: StockSnapshotRepository = Depends(get_snapshot_repository),
) -> list[SnapshotDTO]:
    return ListProductSnapshots(repo).execute(company_id, product_id)


# --- Replenishments ----------------------------------------------------------
@router.get("/replenishments", response_model=list[ReplenishmentDTO])
def list_replenishments(
    company_id: UUID,
    pagination: PaginationParams = Depends(get_pagination),
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ReplenishmentRepository = Depends(get_replenishment_repository),
) -> list[ReplenishmentDTO]:
    return ListReplenishments(repo).execute(
        company_id,
        offset=(pagination.page - 1) * pagination.size,
        limit=pagination.size,
    )


@router.post("/replenishments", response_model=ReplenishmentDTO, status_code=201)
def create_replenishment(
    company_id: UUID,
    request: CreateReplenishmentRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ReplenishmentRepository = Depends(get_replenishment_repository),
) -> ReplenishmentDTO:
    return CreateReplenishment(repo).execute(
        company_id, product_id=request.product_id, quantity=request.quantity
    )


@router.patch("/replenishments/{replenishment_id}", response_model=ReplenishmentDTO)
def update_replenishment(
    company_id: UUID,
    replenishment_id: UUID,
    request: UpdateReplenishmentRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: ReplenishmentRepository = Depends(get_replenishment_repository),
) -> ReplenishmentDTO:
    return UpdateReplenishmentStatus(repo).execute(
        company_id,
        replenishment_id, status=parse_replenishment_status(request.status)
    )


# --- Stockouts ---------------------------------------------------------------
@router.get("/stockouts", response_model=list[StockoutDTO])
def list_stockouts(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: StockoutEventRepository = Depends(get_stockout_repository),
) -> list[StockoutDTO]:
    return ListOpenStockouts(repo).execute(company_id)


@router.post("/stockouts", response_model=StockoutDTO, status_code=201)
def create_stockout(
    company_id: UUID,
    request: CreateStockoutRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: StockoutEventRepository = Depends(get_stockout_repository),
) -> StockoutDTO:
    return CreateStockout(repo).execute(
        company_id, product_id=request.product_id, started_at=request.started_at
    )


@router.post("/stockouts/detect", response_model=list[StockoutDTO], status_code=201)
def detect_stockouts(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    products: ProductRepository = Depends(get_product_repository),
    movements: InventoryMovementRepository = Depends(get_movement_repository),
    stockouts: StockoutEventRepository = Depends(get_stockout_repository),
) -> list[StockoutDTO]:
    return DetectStockouts(
        products=products,
        movements=movements,
        stockouts=stockouts,
    ).execute(company_id)


@router.patch("/stockouts/{stockout_id}", response_model=StockoutDTO)
def close_stockout(
    company_id: UUID,
    stockout_id: UUID,
    request: CloseStockoutRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: StockoutEventRepository = Depends(get_stockout_repository),
) -> StockoutDTO:
    return CloseStockout(repo).execute(company_id, stockout_id, ended_at=request.ended_at)


@router.delete("/stockouts/{stockout_id}", response_model=MessageResponse)
def delete_stockout(company_id: UUID, stockout_id: UUID) -> MessageResponse:
    # TODO: StockoutEventRepository has no delete operation.
    return MessageResponse(message="Not implemented yet")
