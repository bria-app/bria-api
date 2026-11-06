"""Products module — presentation request schemas."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CreateProductRequest(BaseModel):
    # Blank or missing → the company's next correlativo (P-000001...).
    sku: str | None = None
    name: str
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)
    unit_price: Decimal = Field(ge=0)
    currency: str = "PEN"
    description: str = ""
    category_id: UUID | None = None
    unit_of_measure: str = "unit"
    lead_time_days: int = Field(default=0, ge=0)
    safety_stock: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=0, ge=0)
    barcode: str | None = None
    image_url: str | None = None
    custom_attributes: dict[str, Any] = Field(default_factory=dict)
    # Units already on the shelf; posted as an inbound movement valued at unit_cost.
    initial_stock: int = Field(default=0, ge=0)


class UpdateProductRequest(BaseModel):
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    category_id: UUID | None = None
    unit_cost: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    unit_of_measure: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    safety_stock: int | None = Field(default=None, ge=0)
    reorder_point: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    barcode: str | None = None
    image_url: str | None = None
    custom_attributes: dict[str, Any] | None = None


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class ImportProductRowRequest(BaseModel):
    row: int | None = None
    sku: str | None = None
    barcode: str | None = None
    name: str = ""
    category: str | None = None
    unit_cost: Decimal | None = None
    unit_price: Decimal | None = None
    initial_stock: Decimal | None = None
    safety_stock: Decimal | None = None
    reorder_point: Decimal | None = None
    lead_time_days: Decimal | None = None
    unit_of_measure: str | None = None
    custom_attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "sku", "barcode", "category", "unit_cost", "unit_price", "initial_stock", "safety_stock",
        "reorder_point", "lead_time_days", "unit_of_measure", mode="before",
    )
    @classmethod
    def _blank(cls, value: Any) -> Any:
        value = _blank_to_none(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return value


class ImportProductsRequest(BaseModel):
    rows: list[ImportProductRowRequest] = Field(max_length=10000)
    update_existing: bool = False


class CreateCategoryRequest(BaseModel):
    name: str
    description: str = ""
    parent_id: UUID | None = None


class UpdateCategoryRequest(BaseModel):
    name: str | None = None
    description: str | None = None
