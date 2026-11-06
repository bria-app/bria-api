"""Invoicing module — presentation request schemas."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.modules.invoicing.domain.enums import ClientDocType, DocumentType


class InvoiceItemRequest(BaseModel):
    description: str
    quantity: int
    unit_price: Decimal
    discount: Decimal = Decimal("0")
    product_id: UUID | None = None


class CreateInvoiceRequest(BaseModel):
    document_type: DocumentType
    client_doc_type: ClientDocType = ClientDocType.NONE
    client_doc_number: str = ""
    client_name: str = ""
    client_address: str = ""
    items: list[InvoiceItemRequest]
    currency: str = "PEN"
    sale_id: UUID | None = None
    # False keeps the original behaviour (IGV added on top of the unit prices).
    prices_include_igv: bool = False
