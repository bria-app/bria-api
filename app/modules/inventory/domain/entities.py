"""Inventory module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.inventory.domain.enums import MovementType, ReplenishmentStatus
from app.modules.inventory.domain.exceptions import InvalidInventoryError
from app.shared.domain.value_objects import Quantity


@dataclass
class InventoryMovement:
    """Records an inventory movement (in/out/adjustment).

    Quantity is always non-negative; the direction comes from `movement_type`
    (outbound subtracts, inbound/adjustment add). A negative stock adjustment is
    stored as an outbound movement with reference_type "adjustment".
    """

    company_id: UUID
    product_id: UUID
    movement_type: MovementType
    quantity: Quantity
    reason: str
    occurred_at: datetime
    id: UUID | None = None
    # Valuation + traceability (optional for backwards compatibility).
    unit_cost: Decimal | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None

    @property
    def signed_quantity(self) -> int:
        if self.movement_type == MovementType.OUTBOUND:
            return -self.quantity.value
        return self.quantity.value


@dataclass
class StockSnapshot:
    """A point-in-time snapshot of stock for a product."""

    company_id: UUID
    product_id: UUID
    quantity_on_hand: Quantity
    snapshot_at: datetime
    id: UUID | None = None


@dataclass
class Replenishment:
    """A suggested or tracked replenishment order."""

    company_id: UUID
    product_id: UUID
    quantity: Quantity
    status: ReplenishmentStatus = ReplenishmentStatus.SUGGESTED
    id: UUID | None = None


@dataclass
class StockoutEvent:
    """Tracks a period when a product was out of stock."""

    company_id: UUID
    product_id: UUID
    started_at: datetime
    ended_at: datetime | None = None
    id: UUID | None = None

    def duration_days(self) -> int | None:
        """Return duration in days, or None if still open."""
        if self.ended_at is None:
            return None
        delta = self.ended_at - self.started_at
        return delta.days

    def close(self, at: datetime) -> None:
        """Close this stockout event at the given timestamp."""
        if self.ended_at is not None:
            raise InvalidInventoryError(
                message="Este quiebre de stock ya está cerrado."
            )
        if at < self.started_at:
            raise InvalidInventoryError(
                message="La hora de fin no puede ser anterior a la de inicio. Corrígela."
            )
        self.ended_at = at
