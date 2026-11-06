"""Inventory module — presentation request schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateMovementRequest(BaseModel):
    product_id: UUID
    movement_type: str
    quantity: int = Field(gt=0)
    reason: str = ""
    occurred_at: datetime | None = None
    # Inbound only: cost of the received units → updates the weighted-average cost.
    unit_cost: Decimal | None = Field(default=None, ge=0)
    reference_type: str | None = Field(default=None, max_length=20)
    reference_id: UUID | None = None


class StockAdjustmentRequest(BaseModel):
    product_id: UUID
    mode: Literal["set", "delta"]
    quantity: int
    reason: Literal["conteo", "merma", "robo", "vencido", "otro"]
    note: str | None = Field(default=None, max_length=180)


class CreateSnapshotRequest(BaseModel):
    product_id: UUID
    quantity_on_hand: int
    snapshot_at: datetime | None = None


class CreateReplenishmentRequest(BaseModel):
    product_id: UUID
    quantity: int


class UpdateReplenishmentRequest(BaseModel):
    status: str


class CreateStockoutRequest(BaseModel):
    product_id: UUID
    started_at: datetime | None = None


class CloseStockoutRequest(BaseModel):
    ended_at: datetime | None = None
