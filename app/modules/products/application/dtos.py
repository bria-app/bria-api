"""Products module — application output DTOs."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.products.domain.entities import Category, Product


class CategoryDTO(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    description: str
    parent_id: UUID | None

    @classmethod
    def from_entity(cls, category: Category) -> CategoryDTO:
        assert category.id is not None
        return cls(
            id=category.id,
            company_id=category.company_id,
            name=category.name,
            description=category.description,
            parent_id=category.parent_id,
        )


class ProductAlertDTO(BaseModel):
    """An own column's alert that fired for the product («Por vencer», «Sin marca»...)."""

    key: str  # the column key inside custom_attributes
    column: str  # the column label, e.g. "Vencimiento"
    label: str  # the alert label, e.g. "Por vencer"
    tone: Literal["warning", "danger"]


class ProductDTO(BaseModel):
    id: UUID
    company_id: UUID
    sku: str
    name: str
    description: str
    category_id: UUID | None
    # Weighted-average cost. None when the caller may not see costs (sellers).
    unit_cost: Decimal | None
    unit_price: Decimal
    currency: str
    unit_of_measure: str
    lead_time_days: int
    safety_stock: int
    reorder_point: int
    is_active: bool
    barcode: str | None = None
    image_url: str | None = None
    custom_attributes: dict[str, Any] = Field(default_factory=dict)
    last_cost: Decimal | None = None
    # Alerts of the company's own columns (rules.alert), ordered like the columns.
    alerts: list[ProductAlertDTO] = Field(default_factory=list)

    @classmethod
    def from_entity(cls, product: Product) -> ProductDTO:
        assert product.id is not None
        return cls(
            id=product.id,
            company_id=product.company_id,
            sku=product.sku.value,
            name=product.name,
            description=product.description,
            category_id=product.category_id,
            unit_cost=product.unit_cost.amount,
            unit_price=product.unit_price.amount,
            currency=product.unit_cost.currency,
            unit_of_measure=product.unit_of_measure,
            lead_time_days=product.lead_time_days,
            safety_stock=product.safety_stock,
            reorder_point=product.reorder_point,
            is_active=product.is_active,
            barcode=product.barcode,
            image_url=product.image_url,
            custom_attributes=dict(product.custom_attributes or {}),
            last_cost=product.last_cost.amount if product.last_cost else None,
        )

    def without_costs(self) -> ProductDTO:
        """Same product with every cost field blanked (the fields stay, as null)."""
        return self.model_copy(update={"unit_cost": None, "last_cost": None})


# --- Smart import ------------------------------------------------------------
class ImportRowError(BaseModel):
    row: int
    message: str


class ImportProductsResultDTO(BaseModel):
    created: int
    updated: int
    errors: list[ImportRowError]
    categories_created: int = 0


# --- Product 360 timeline ----------------------------------------------------
TimelineKind = Literal["sale", "restock", "adjustment", "lost_sale"]


class TimelineEventDTO(BaseModel):
    id: UUID
    kind: TimelineKind
    occurred_at: datetime
    quantity: int
    # sale
    unit_price: Decimal | None = None
    total: Decimal | None = None
    order_id: UUID | None = None
    order_number: int | None = None
    batch_id: UUID | None = None
    seller_name: str | None = None
    # restock
    unit_cost: Decimal | None = None
    supplier_id: UUID | None = None
    supplier_name: str | None = None
    document_number: str | None = None
    purchase_id: UUID | None = None
    # adjustment / other movements
    movement_type: str | None = None
    signed_quantity: int | None = None
    reason: str | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None
    # lost sale (quiebre)
    requested_quantity: int | None = None
    available_quantity: int | None = None
    source: str | None = None


class TimelineStatsDTO(BaseModel):
    stock_on_hand: int
    units_sold_30d: int
    units_sold_90d: int
    units_sold_365d: int
    revenue_365d: Decimal
    avg_price_365d: Decimal | None
    gross_margin_pct: float | None
    coverage_days: float | None
    lost_sale_attempts: int
    lost_units: int
    lost_sale_attempts_30d: int
    restock_count: int
    last_restock_at: date | None
    last_sale_at: date | None


class StockPointDTO(BaseModel):
    date: date
    stock: int
    inbound: int
    outbound: int


class MonthlySalesPointDTO(BaseModel):
    month: str  # yyyy-mm
    units: int
    revenue: Decimal
    lost_units: int = 0


class WeeklySalesPointDTO(BaseModel):
    week_start: date  # Monday
    units: int
    revenue: Decimal
    stockout_days: int  # days that ended with nothing on hand
    lost_units: int


class ProductTimelineDTO(BaseModel):
    product: ProductDTO
    category_path: list[str]
    stats: TimelineStatsDTO
    events: list[TimelineEventDTO]
    events_truncated: bool
    stock_series: list[StockPointDTO]
    monthly_sales: list[MonthlySalesPointDTO]
    weekly_sales: list[WeeklySalesPointDTO]
    weekday_units: list[int]  # units sold Monday..Sunday over the weekly window

    def without_costs(self) -> ProductTimelineDTO:
        """Timeline without costs or margins: unit costs, restock totals (what was paid
        to the supplier) and the gross margin come back as null."""
        events = [
            e.model_copy(
                update={"unit_cost": None, **({"total": None} if e.kind == "restock" else {})}
            )
            for e in self.events
        ]
        return self.model_copy(
            update={
                "product": self.product.without_costs(),
                "events": events,
                "stats": self.stats.model_copy(update={"gross_margin_pct": None}),
            }
        )
