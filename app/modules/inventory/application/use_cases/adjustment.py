"""Inventory module — manual stock adjustments (conteo, merma, robo, vencido...).

The ledger only stores non-negative quantities, so the direction is carried by the
movement type: a positive correction is an `adjustment` movement (adds) and a negative
one is an `outbound` movement; both are tagged reference_type="adjustment" so they are
never mistaken for sales. Adjustments are valued at the current average cost and do
not change it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.modules.inventory.application.dtos import AdjustmentResultDTO, MovementDTO
from app.modules.inventory.application.ports import StockReader
from app.modules.inventory.domain.entities import InventoryMovement
from app.modules.inventory.domain.enums import AdjustmentMode, AdjustmentReason, MovementType
from app.modules.inventory.domain.exceptions import InvalidInventoryError
from app.modules.inventory.domain.repositories import InventoryMovementRepository
from app.modules.products.domain.exceptions import ProductNotFoundError
from app.modules.products.domain.repositories import ProductRepository
from app.shared.domain.value_objects import Quantity

ADJUSTMENT_REFERENCE = "adjustment"


class AdjustStock:
    def __init__(
        self,
        *,
        products: ProductRepository,
        movements: InventoryMovementRepository,
        stock: StockReader,
    ) -> None:
        self._products = products
        self._movements = movements
        self._stock = stock

    def execute(
        self,
        company_id: UUID,
        *,
        product_id: UUID,
        mode: AdjustmentMode,
        quantity: int,
        reason: AdjustmentReason,
        note: str | None = None,
    ) -> AdjustmentResultDTO:
        product = self._products.get_by_id(product_id)
        if product is None or product.company_id != company_id:
            raise ProductNotFoundError(product_id)

        previous = self._stock.on_hand(company_id, product_id)
        if mode == AdjustmentMode.SET:
            if quantity < 0:
                raise InvalidInventoryError(message="El stock contado no puede ser negativo.")
            delta = quantity - previous
        else:
            if quantity == 0:
                raise InvalidInventoryError(message="Indica cuántas unidades sumar o restar.")
            delta = quantity

        new_stock = previous + delta
        if new_stock < 0:
            raise InvalidInventoryError(
                message=f"El ajuste dejaría el stock en negativo: hay {previous} unidades disponibles."
            )
        if reason.only_reduces and delta > 0:
            raise InvalidInventoryError(
                message=f"Un ajuste por '{reason.label.lower()}' solo puede reducir el stock."
            )

        if delta == 0:
            return AdjustmentResultDTO(
                product_id=product_id, previous_stock=previous, new_stock=previous, delta=0, movement=None
            )

        text = f"Ajuste · {reason.label}"
        if note and note.strip():
            text = f"{text} · {note.strip()}"
        movement = InventoryMovement(
            company_id=company_id,
            product_id=product_id,
            movement_type=MovementType.ADJUSTMENT if delta > 0 else MovementType.OUTBOUND,
            quantity=Quantity(abs(delta)),
            reason=text[:255],
            occurred_at=datetime.now(timezone.utc),
            unit_cost=product.unit_cost.amount,
            reference_type=ADJUSTMENT_REFERENCE,
        )
        saved = self._movements.add(movement)
        return AdjustmentResultDTO(
            product_id=product_id,
            previous_stock=previous,
            new_stock=new_stock,
            delta=delta,
            movement=MovementDTO.from_entity(saved),
        )
