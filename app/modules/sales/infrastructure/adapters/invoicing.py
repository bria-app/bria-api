"""Sales module — adapter that issues the ticket's comprobante through the invoicing module."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.invoicing.application.use_cases.invoice import CreateInvoice, GetInvoice, VoidInvoice
from app.modules.invoicing.domain.enums import ClientDocType, DocumentType, InvoiceStatus
from app.modules.invoicing.infrastructure.persistence.repositories import SqlInvoiceRepository
from app.modules.sales.domain.entities import SalesOrder
from app.modules.sales.domain.repositories import IssuedInvoice


class InvoicingModuleIssuer:
    def __init__(self, session: Session) -> None:
        self._invoices = SqlInvoiceRepository(session)

    def issue(self, order: SalesOrder) -> IssuedInvoice:
        dto = CreateInvoice(self._invoices).execute(
            order.company_id,
            document_type=DocumentType(order.document_type.value),
            client_doc_type=ClientDocType(order.client_doc_type.value),
            client_doc_number=order.client_doc_number,
            client_name=order.client_name,
            client_address=order.client_address,
            items=[
                {
                    "description": line.product_name or line.sku or "Producto",
                    "quantity": line.quantity,
                    "unit_price": str(line.unit_price),
                    "discount": str(line.discount),
                    "product_id": str(line.product_id),
                }
                for line in order.lines
            ],
            currency=order.currency,
            sale_id=order.id,
            prices_include_igv=True,  # retail prices already include IGV
            issued_at=order.sold_at,
        )
        return IssuedInvoice(id=dto.id, document_number=dto.document_number)

    def void(self, company_id: UUID, invoice_id: UUID) -> None:
        current = GetInvoice(self._invoices).execute(company_id, invoice_id)
        if current.status == InvoiceStatus.ANULADA:
            return
        VoidInvoice(self._invoices).execute(company_id, invoice_id)
