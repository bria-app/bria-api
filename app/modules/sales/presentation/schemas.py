"""Sales module — presentation request schemas."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.modules.sales.domain.enums import ClientDocType, PaymentMethod, SalesDocumentType


class CreateSaleRequest(BaseModel):
    product_id: UUID
    sale_date: date
    quantity: int
    unit_price: Decimal
    currency: str = "PEN"
    batch_id: UUID | None = None


class BulkSalesItem(BaseModel):
    product_id: UUID
    sale_date: date
    quantity: int
    unit_price: Decimal
    currency: str = "PEN"
    batch_id: UUID | None = None


class BulkSalesRequest(BaseModel):
    items: list[BulkSalesItem]


class CreateSalesBatchRequest(BaseModel):
    source_file: str
    period_start: date | None = None
    period_end: date | None = None


# --- POS -------------------------------------------------------------------------
class SalesOrderItemRequest(BaseModel):
    product_id: UUID
    quantity: int
    unit_price: Decimal
    discount: Decimal = Decimal("0")


class CreateSalesOrderRequest(BaseModel):
    """Retail prices include IGV. Seller and date/time come from the session, not the body."""

    items: list[SalesOrderItemRequest]
    document_type: SalesDocumentType = SalesDocumentType.BOLETA
    client_doc_type: ClientDocType = ClientDocType.NONE
    client_doc_number: str = ""
    client_name: str = ""
    client_address: str = ""
    payment_method: PaymentMethod = PaymentMethod.EFECTIVO
    amount_received: Decimal | None = None
    notes: str = ""


class VoidSalesOrderRequest(BaseModel):
    reason: str = ""


class RecordLostSaleRequest(BaseModel):
    product_id: UUID
    requested_quantity: int
    available_quantity: int = 0
    source: str = "pos"
