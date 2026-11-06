"""Purchases module — application output DTOs."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.modules.purchases.domain.entities import Purchase, StockReceipt


class PurchaseDTO(BaseModel):
    id: UUID
    company_id: UUID
    supplier_id: UUID
    product_id: UUID
    purchase_date: date
    quantity: int
    unit_cost: Decimal
    total_amount: Decimal
    currency: str
    document_number: str = ""
    notes: str = ""
    import_batch_id: UUID | None = None

    @classmethod
    def from_entity(cls, purchase: Purchase) -> PurchaseDTO:
        assert purchase.id is not None
        return cls(
            id=purchase.id,
            company_id=purchase.company_id,
            supplier_id=purchase.supplier_id,
            product_id=purchase.product_id,
            purchase_date=purchase.purchase_date,
            quantity=purchase.quantity.value,
            unit_cost=purchase.unit_cost.amount,
            total_amount=purchase.total_amount.amount,
            currency=purchase.unit_cost.currency,
            document_number=purchase.document_number,
            notes=purchase.notes,
            import_batch_id=purchase.import_batch_id,
        )


class PurchaseLineDTO(BaseModel):
    """A purchase line with supplier and product names resolved."""

    id: UUID
    company_id: UUID
    supplier_id: UUID
    supplier_name: str
    supplier_ruc: str
    product_id: UUID
    product_name: str
    sku: str
    purchase_date: date
    quantity: int
    unit_cost: Decimal
    total_amount: Decimal
    currency: str
    document_number: str
    notes: str
    import_batch_id: UUID | None
    document_id: str
    created_at: datetime | None = None
    # True when the supplier was deleted: supplier_id stays, but its page no longer exists.
    supplier_deleted: bool = False


class PurchaseDocumentDTO(BaseModel):
    """One supplier document (factura) = a group of purchase lines."""

    document_id: str
    supplier_id: UUID
    supplier_name: str
    supplier_ruc: str
    document_number: str
    purchase_date: date
    notes: str
    lines: int
    units: int
    total: Decimal
    created_at: datetime | None = None
    # True when the supplier was deleted: supplier_id stays, but its page no longer exists.
    supplier_deleted: bool = False


class PurchaseDocumentDetailDTO(BaseModel):
    document_id: str
    supplier_id: UUID
    supplier_name: str
    supplier_ruc: str
    document_number: str
    purchase_date: date
    notes: str
    lines: list[PurchaseLineDTO]
    units: int
    total: Decimal
    created_at: datetime | None = None
    # True when the supplier was deleted: supplier_id stays, but its page no longer exists.
    supplier_deleted: bool = False


class PurchaseDocumentPageDTO(BaseModel):
    items: list[PurchaseDocumentDTO]
    total: int
    page: int
    size: int
    pages: int


class NewProductDTO(BaseModel):
    row: int | None = None
    product_id: UUID
    name: str
    sku: str


class StockChangeDTO(BaseModel):
    product_id: UUID
    sku: str
    name: str
    quantity: int
    previous_stock: int
    new_stock: int
    previous_avg_cost: Decimal
    new_avg_cost: Decimal

    @classmethod
    def build(cls, receipt: StockReceipt, sku: str, name: str) -> StockChangeDTO:
        return cls(
            product_id=receipt.product_id,
            sku=sku,
            name=name,
            quantity=receipt.quantity,
            previous_stock=receipt.previous_stock,
            new_stock=receipt.new_stock,
            previous_avg_cost=receipt.previous_avg_cost,
            new_avg_cost=receipt.new_avg_cost,
        )


class PurchaseBatchResultDTO(BaseModel):
    batch_id: UUID
    document_number: str
    purchase_date: date
    costs_include_igv: bool
    lines: list[PurchaseDTO]
    new_products: list[NewProductDTO]
    stock_changes: list[StockChangeDTO]
    units: int
    subtotal: Decimal
    igv: Decimal
    total: Decimal


class ImportErrorDTO(BaseModel):
    row: int
    message: str


class PurchaseImportResultDTO(BaseModel):
    batch_id: UUID | None
    batch_ids: list[UUID]
    created_lines: int
    matched: int
    new_products: list[NewProductDTO]
    errors: list[ImportErrorDTO]
    units: int
    subtotal: Decimal
    igv: Decimal
    total: Decimal


class PurchaseCatalogItemDTO(BaseModel):
    """Product as shown in the purchase form: code, stock and costs."""

    id: UUID
    sku: str
    name: str
    barcode: str | None
    category_id: UUID | None
    unit_cost: Decimal
    last_cost: Decimal | None
    unit_price: Decimal
    stock_on_hand: int
    is_active: bool
