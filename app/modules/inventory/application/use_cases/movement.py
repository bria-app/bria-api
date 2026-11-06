"""Inventory module — movement and derived-stock use cases."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.modules.inventory.application.dtos import MovementDTO, StockLevelDTO
from app.modules.inventory.application.ports import InboundCosting
from app.modules.inventory.domain.entities import InventoryMovement
from app.modules.inventory.domain.enums import MovementType
from app.modules.inventory.domain.exceptions import (
    InvalidInventoryError,
    InventoryMovementNotFoundError,
)
from app.modules.inventory.domain.repositories import InventoryMovementRepository
from app.modules.inventory.domain.services import compute_stock_on_hand
from app.modules.products.domain.exceptions import ProductNotFoundError
from app.modules.products.domain.repositories import ProductRepository
from app.shared.domain.value_objects import Quantity

_PAGE = 200


def _stock_on_hand(movements: InventoryMovementRepository, product_id: UUID) -> int:
    """Sum the full movement ledger for one product into a current on-hand quantity."""
    collected: list[InventoryMovement] = []
    offset = 0
    while True:
        page = movements.list_by_product(product_id, offset, _PAGE)
        collected.extend(page)
        if len(page) < _PAGE:
            break
        offset += _PAGE
    return compute_stock_on_hand(collected)


class CreateMovement:
    """Registers a movement. Inbound movements with a unit cost update the product's
    weighted-average cost (via the costing port) before the movement is stored."""

    def __init__(
        self,
        movements: InventoryMovementRepository,
        costing: InboundCosting | None = None,
    ) -> None:
        self._movements = movements
        self._costing = costing

    def execute(
        self,
        company_id: UUID,
        *,
        product_id: UUID,
        movement_type: MovementType,
        quantity: int,
        reason: str = "",
        occurred_at: datetime | None = None,
        unit_cost: Decimal | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
    ) -> MovementDTO:
        if quantity <= 0:
            raise InvalidInventoryError(message="La cantidad debe ser mayor a cero.")
        if unit_cost is not None and unit_cost < 0:
            raise InvalidInventoryError(message="El costo unitario no puede ser negativo.")
        if movement_type == MovementType.INBOUND and unit_cost is not None and self._costing is not None:
            self._costing.apply(company_id, product_id, quantity, unit_cost)
        movement = InventoryMovement(
            company_id=company_id,
            product_id=product_id,
            movement_type=movement_type,
            quantity=Quantity(quantity),
            reason=reason,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            unit_cost=unit_cost,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        return MovementDTO.from_entity(self._movements.add(movement))


class GetMovement:
    def __init__(self, movements: InventoryMovementRepository) -> None:
        self._movements = movements

    def execute(self, company_id: UUID, movement_id: UUID) -> MovementDTO:
        movement = self._movements.get_by_id(movement_id)
        if movement is None or movement.company_id != company_id:
            raise InventoryMovementNotFoundError(
                message="No encontramos ese movimiento. Actualiza la página e inténtalo de nuevo."
            )
        return MovementDTO.from_entity(movement)


class ListMovements:
    def __init__(self, movements: InventoryMovementRepository) -> None:
        self._movements = movements

    def execute(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
        reference_type: str | None = None,
    ) -> list[MovementDTO]:
        kind = (reference_type or "").strip() or None
        return [
            MovementDTO.from_entity(m)
            for m in self._movements.list_by_company(company_id, offset, limit, reference_type=kind)
        ]


class GetCurrentStock:
    """Derive current stock for a product from its full movement ledger."""

    def __init__(
        self, movements: InventoryMovementRepository, products: ProductRepository
    ) -> None:
        self._movements = movements
        self._products = products

    def execute(self, company_id: UUID, product_id: UUID) -> StockLevelDTO:
        product = self._products.get_by_id(product_id)
        if product is None or product.company_id != company_id:
            raise ProductNotFoundError(product_id)
        return StockLevelDTO(
            product_id=product_id,
            quantity_on_hand=_stock_on_hand(self._movements, product_id),
        )


class GetCompanyStockLevels:
    """Current on-hand stock for every active product of a company."""

    def __init__(
        self,
        *,
        products: ProductRepository,
        movements: InventoryMovementRepository,
    ) -> None:
        self._products = products
        self._movements = movements

    def execute(self, company_id: UUID) -> list[StockLevelDTO]:
        return [
            StockLevelDTO(
                product_id=product.id,
                quantity_on_hand=_stock_on_hand(self._movements, product.id),
            )
            for product in self._products.list_active(company_id)
            if product.id is not None
        ]
