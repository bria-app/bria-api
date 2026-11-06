"""Inventory module — application output DTOs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.inventory.domain.entities import (
    InventoryMovement,
    Replenishment,
    StockoutEvent,
    StockSnapshot,
)


class MovementDTO(BaseModel):
    id: UUID
    company_id: UUID
    product_id: UUID
    movement_type: str
    quantity: int
    signed_quantity: int
    reason: str
    occurred_at: datetime
    unit_cost: Decimal | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None

    @classmethod
    def from_entity(cls, m: InventoryMovement) -> MovementDTO:
        assert m.id is not None
        return cls(
            id=m.id,
            company_id=m.company_id,
            product_id=m.product_id,
            movement_type=m.movement_type.value,
            quantity=m.quantity.value,
            signed_quantity=m.signed_quantity,
            reason=m.reason,
            occurred_at=m.occurred_at,
            unit_cost=m.unit_cost,
            reference_type=m.reference_type,
            reference_id=m.reference_id,
        )


class StockLevelDTO(BaseModel):
    product_id: UUID
    quantity_on_hand: int


class AdjustmentResultDTO(BaseModel):
    product_id: UUID
    previous_stock: int
    new_stock: int
    delta: int
    movement: MovementDTO | None


class SnapshotDTO(BaseModel):
    id: UUID
    company_id: UUID
    product_id: UUID
    quantity_on_hand: int
    snapshot_at: datetime

    @classmethod
    def from_entity(cls, s: StockSnapshot) -> SnapshotDTO:
        assert s.id is not None
        return cls(
            id=s.id,
            company_id=s.company_id,
            product_id=s.product_id,
            quantity_on_hand=s.quantity_on_hand.value,
            snapshot_at=s.snapshot_at,
        )


class ReplenishmentDTO(BaseModel):
    id: UUID
    company_id: UUID
    product_id: UUID
    quantity: int
    status: str

    @classmethod
    def from_entity(cls, r: Replenishment) -> ReplenishmentDTO:
        assert r.id is not None
        return cls(
            id=r.id,
            company_id=r.company_id,
            product_id=r.product_id,
            quantity=r.quantity.value,
            status=r.status.value,
        )


class StockoutDTO(BaseModel):
    id: UUID
    company_id: UUID
    product_id: UUID
    started_at: datetime
    ended_at: datetime | None
    duration_days: int | None

    @classmethod
    def from_entity(cls, e: StockoutEvent) -> StockoutDTO:
        assert e.id is not None
        return cls(
            id=e.id,
            company_id=e.company_id,
            product_id=e.product_id,
            started_at=e.started_at,
            ended_at=e.ended_at,
            duration_days=e.duration_days(),
        )


# --- Overview (main inventory table) ------------------------------------------
StockStatus = Literal["sin_stock", "critico", "reordenar", "ok"]


class InventoryOverviewItemDTO(BaseModel):
    id: UUID
    sku: str
    name: str
    description: str
    barcode: str | None
    image_url: str | None
    category_id: UUID | None
    category_name: str | None
    category_path: list[str]
    # Cost fields are None when the caller may not see costs (role seller).
    unit_cost: Decimal | None
    last_cost: Decimal | None
    unit_price: Decimal
    currency: str
    unit_of_measure: str
    lead_time_days: int
    safety_stock: int
    reorder_point: int
    is_active: bool
    custom_attributes: dict[str, Any] = Field(default_factory=dict)
    stock_on_hand: int
    stock_value: Decimal | None
    retail_value: Decimal
    status: StockStatus
    last_movement_at: datetime | None
    units_sold_30d: int
    coverage_days: float | None
    lost_sales_30d: int


class StatusCountsDTO(BaseModel):
    sin_stock: int = 0
    critico: int = 0
    reordenar: int = 0
    ok: int = 0


class InventoryTotalsDTO(BaseModel):
    products: int
    units_on_hand: int
    inventory_value_cost: Decimal | None
    inventory_value_retail: Decimal
    potential_margin: Decimal | None
    status_counts: StatusCountsDTO


class InventoryOverviewDTO(BaseModel):
    items: list[InventoryOverviewItemDTO]
    totals: InventoryTotalsDTO
    generated_at: datetime


# --- Valuation ---------------------------------------------------------------
class ValuationGroupDTO(BaseModel):
    category_id: UUID | None
    name: str
    path: list[str]
    products: int
    units: int
    value_cost: Decimal | None
    value_retail: Decimal
    # Share of the inventory value at cost; None with the costs.
    share_pct: float | None


class InventoryValuationDTO(BaseModel):
    totals: InventoryTotalsDTO
    by_category: list[ValuationGroupDTO]
    by_brand: list[ValuationGroupDTO]
