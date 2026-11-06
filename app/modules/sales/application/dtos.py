"""Sales module — application output DTOs."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.modules.sales.domain.entities import CatalogProduct, LostSale, Sale, SalesBatch


class SaleDTO(BaseModel):
    id: UUID
    company_id: UUID
    product_id: UUID
    batch_id: UUID | None
    sale_date: date
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    currency: str
    # POS lines only (None / "" for imported history).
    order_id: UUID | None = None
    seller_id: UUID | None = None
    seller_name: str = ""
    unit_cost: Decimal | None = None
    # Product labels, as SalesOrderLineDTO has them ("" when not loaded).
    product_name: str = ""
    sku: str = ""

    @classmethod
    def from_entity(cls, sale: Sale) -> SaleDTO:
        assert sale.id is not None
        return cls(
            id=sale.id,
            company_id=sale.company_id,
            product_id=sale.product_id,
            batch_id=sale.batch_id,
            sale_date=sale.sale_date,
            quantity=sale.quantity.value,
            unit_price=sale.unit_price.amount,
            total_amount=sale.total_amount.amount,
            currency=sale.unit_price.currency,
            order_id=sale.order_id,
            seller_id=sale.seller_id,
            seller_name=sale.seller_name,
            unit_cost=sale.unit_cost,
            product_name=sale.product_name,
            sku=sale.sku,
        )


class SalesBatchDTO(BaseModel):
    id: UUID
    company_id: UUID
    source_file: str
    status: str
    row_count: int
    period_start: date | None
    period_end: date | None

    @classmethod
    def from_entity(cls, batch: SalesBatch) -> SalesBatchDTO:
        assert batch.id is not None
        return cls(
            id=batch.id,
            company_id=batch.company_id,
            source_file=batch.source_file,
            status=batch.status.value,
            row_count=batch.row_count,
            period_start=batch.period.start if batch.period else None,
            period_end=batch.period.end if batch.period else None,
        )


# --- POS -----------------------------------------------------------------------
class SalesOrderLineDTO(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    discount: Decimal
    line_total: Decimal
    unit_cost: Decimal | None


class SalesOrderDTO(BaseModel):
    id: UUID
    company_id: UUID
    order_number: int
    document_type: str
    document_number: str
    invoice_id: UUID | None
    invoice_status: str | None
    client_doc_type: str
    client_doc_number: str
    client_name: str
    client_address: str
    seller_id: UUID | None
    seller_name: str
    payment_method: str
    amount_received: Decimal | None
    change: Decimal | None
    discount_total: Decimal
    subtotal: Decimal
    igv: Decimal
    total: Decimal
    currency: str
    items_count: int
    units: int
    # None when the caller may not see costs (role seller).
    cost_total: Decimal | None
    gross_margin: Decimal | None
    status: str
    notes: str
    sold_at: datetime
    lines: list[SalesOrderLineDTO]


class SalesOrderRowDTO(BaseModel):
    id: UUID
    order_number: int
    sold_at: datetime
    document_type: str
    document_number: str
    invoice_status: str | None
    client_doc_type: str
    client_doc_number: str
    client_name: str
    seller_id: UUID | None
    seller_name: str
    payment_method: str
    items_count: int
    units: int
    subtotal: Decimal
    igv: Decimal
    total: Decimal
    # None when the caller may not see costs (role seller).
    cost_total: Decimal | None
    margin: Decimal | None
    status: str


class SalesOrderPageDTO(BaseModel):
    items: list[SalesOrderRowDTO]
    total: int
    page: int
    size: int
    pages: int


class PaymentMethodBreakdownDTO(BaseModel):
    payment_method: str
    orders: int
    total: Decimal


class SellerBreakdownDTO(BaseModel):
    seller_id: UUID | None
    seller_name: str
    orders: int
    units: int
    total: Decimal


class DocumentTypeBreakdownDTO(BaseModel):
    document_type: str
    orders: int
    total: Decimal


class DailySalesDTO(BaseModel):
    date: date
    orders: int
    total: Decimal


class TopProductDTO(BaseModel):
    product_id: UUID
    name: str
    sku: str
    units: int
    total: Decimal


class SalesSummaryDTO(BaseModel):
    """Completed tickets only.

    revenue = Σ total (IGV included); revenue_net = Σ op. gravada (without IGV);
    gross_margin = revenue_net − Σ quantity × unit_cost (cost at the moment of sale).
    """

    date_from: date
    date_to: date
    revenue: Decimal
    revenue_net: Decimal
    igv: Decimal
    orders: int
    avg_ticket: Decimal
    units: int
    # None when the caller may not see costs (role seller).
    cost_total: Decimal | None
    gross_margin: Decimal | None
    margin_pct: Decimal | None
    voided_orders: int
    by_payment_method: list[PaymentMethodBreakdownDTO]
    by_seller: list[SellerBreakdownDTO]
    by_document_type: list[DocumentTypeBreakdownDTO]
    by_day: list[DailySalesDTO]
    top_products: list[TopProductDTO]


class CatalogProductDTO(BaseModel):
    id: UUID
    sku: str
    name: str
    description: str
    barcode: str | None
    image_url: str | None
    unit_price: Decimal
    currency: str
    unit_of_measure: str
    category_id: UUID | None
    category_name: str | None
    custom_attributes: dict[str, Any]
    stock_on_hand: int
    reorder_point: int
    safety_stock: int
    is_active: bool

    @classmethod
    def from_entity(cls, p: CatalogProduct) -> CatalogProductDTO:
        return cls(
            id=p.id,
            sku=p.sku,
            name=p.name,
            description=p.description,
            barcode=p.barcode,
            image_url=p.image_url,
            unit_price=p.unit_price,
            currency=p.currency,
            unit_of_measure=p.unit_of_measure,
            category_id=p.category_id,
            category_name=p.category_name,
            custom_attributes=p.custom_attributes or {},
            stock_on_hand=p.stock_on_hand,
            reorder_point=p.reorder_point,
            safety_stock=p.safety_stock,
            is_active=p.is_active,
        )


class LostSaleDTO(BaseModel):
    id: UUID
    company_id: UUID
    product_id: UUID
    product_name: str = ""
    sku: str = ""
    requested_quantity: int
    available_quantity: int
    seller_id: UUID | None
    seller_name: str
    source: str
    occurred_at: datetime

    @classmethod
    def from_entity(cls, ls: LostSale, product_name: str = "", sku: str = "") -> LostSaleDTO:
        assert ls.id is not None
        return cls(
            id=ls.id,
            company_id=ls.company_id,
            product_id=ls.product_id,
            product_name=product_name,
            sku=sku,
            requested_quantity=ls.requested_quantity,
            available_quantity=ls.available_quantity,
            seller_id=ls.seller_id,
            seller_name=ls.seller_name,
            source=ls.source,
            occurred_at=ls.occurred_at,
        )
