"""Sales module — stock ledger adapter over inventory movements."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.inventory.infrastructure.persistence.models import InventoryMovementModel
from app.modules.inventory.infrastructure.persistence.queries import stock_on_hand


class SqlStockLedger:
    def __init__(self, session: Session) -> None:
        self._session = session

    def on_hand(self, company_id: UUID, product_id: UUID) -> int:
        return stock_on_hand(self._session, company_id, product_id)

    def record(
        self,
        company_id: UUID,
        product_id: UUID,
        *,
        movement_type: str,
        quantity: int,
        unit_cost: Decimal | None,
        reason: str,
        reference_type: str,
        reference_id: UUID,
        occurred_at: datetime,
    ) -> None:
        self._session.add(
            InventoryMovementModel(
                company_id=company_id,
                product_id=product_id,
                movement_type=movement_type,
                quantity=quantity,
                reason=reason[:255],
                occurred_at=occurred_at,
                unit_cost=unit_cost,
                reference_type=reference_type,
                reference_id=reference_id,
            )
        )
        self._session.flush()

    def units_taken_out(self, company_id: UUID, reference_id: UUID) -> dict[UUID, int]:
        rows = self._session.execute(
            select(InventoryMovementModel.product_id, func.sum(InventoryMovementModel.quantity))
            .where(
                InventoryMovementModel.company_id == company_id,
                InventoryMovementModel.reference_type == "sale",
                InventoryMovementModel.reference_id == reference_id,
                InventoryMovementModel.movement_type == "outbound",
            )
            .group_by(InventoryMovementModel.product_id)
        ).all()
        return {pid: int(qty or 0) for pid, qty in rows if qty}
