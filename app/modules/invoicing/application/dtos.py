"""Invoicing module — application output DTOs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.modules.invoicing.domain.entities import Invoice, InvoiceItem
from app.modules.invoicing.domain.enums import ClientDocType, DocumentType, InvoiceStatus


class InvoiceItemDTO(BaseModel):
    product_id: UUID | None
    description: str
    quantity: int
    unit_price: Decimal
    discount: Decimal
    subtotal: Decimal

    @classmethod
    def from_entity(cls, item: InvoiceItem) -> InvoiceItemDTO:
        return cls(
            product_id=item.product_id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            discount=item.discount,
            subtotal=item.subtotal,
        )


class InvoiceDTO(BaseModel):
    id: UUID
    company_id: UUID
    document_type: DocumentType
    series: str
    correlativo: int
    document_number: str
    client_doc_type: ClientDocType
    client_doc_number: str
    client_name: str
    client_address: str
    items: list[InvoiceItemDTO]
    subtotal: Decimal
    igv: Decimal
    total: Decimal
    currency: str
    status: InvoiceStatus
    issued_at: datetime
    sale_id: UUID | None

    @classmethod
    def from_entity(cls, invoice: Invoice) -> InvoiceDTO:
        assert invoice.id is not None
        return cls(
            id=invoice.id,
            company_id=invoice.company_id,
            document_type=invoice.document_type,
            series=invoice.series,
            correlativo=invoice.correlativo,
            document_number=invoice.document_number,
            client_doc_type=invoice.client_doc_type,
            client_doc_number=invoice.client_doc_number,
            client_name=invoice.client_name,
            client_address=invoice.client_address,
            items=[InvoiceItemDTO.from_entity(i) for i in invoice.items],
            subtotal=invoice.subtotal,
            igv=invoice.igv,
            total=invoice.total,
            currency=invoice.currency,
            status=invoice.status,
            issued_at=invoice.issued_at,
            sale_id=invoice.sale_id,
        )
