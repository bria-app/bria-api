"""Invoicing module — use cases for the Invoice aggregate."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.modules.invoicing.application.dtos import InvoiceDTO
from app.modules.invoicing.domain.entities import Invoice, InvoiceItem
from app.modules.invoicing.domain.enums import DEFAULT_SERIES, ClientDocType, DocumentType
from app.modules.invoicing.domain.exceptions import InvoiceNotFoundError
from app.modules.invoicing.domain.repositories import InvoiceRepository
from app.modules.invoicing.domain.services import compute_totals, validate_client


class CreateInvoice:
    """Issues a boleta/factura.

    `prices_include_igv=True` treats unit prices as retail prices with IGV included
    (the POS ticket total equals the comprobante total); the default keeps the
    original behaviour of adding 18% IGV on top.
    """

    def __init__(self, invoices: InvoiceRepository) -> None:
        self._invoices = invoices

    def execute(
        self,
        company_id: UUID,
        *,
        document_type: DocumentType,
        client_doc_type: ClientDocType,
        client_doc_number: str,
        client_name: str,
        items: list[dict[str, object]],
        currency: str = "PEN",
        sale_id: UUID | None = None,
        prices_include_igv: bool = False,
        client_address: str = "",
        issued_at: datetime | None = None,
    ) -> InvoiceDTO:
        line_items = [
            InvoiceItem(
                description=str(it["description"]),
                quantity=int(str(it["quantity"])),
                unit_price=Decimal(str(it["unit_price"])),
                product_id=UUID(str(it["product_id"])) if it.get("product_id") else None,
                discount=Decimal(str(it.get("discount") or "0")),
            )
            for it in items
        ]
        subtotal, igv, total = compute_totals(line_items, prices_include_igv=prices_include_igv)
        validate_client(document_type, client_doc_type, client_doc_number, client_name, total)

        series = DEFAULT_SERIES[document_type]
        correlativo = self._invoices.next_correlativo(company_id, series)

        invoice = Invoice(
            company_id=company_id,
            document_type=document_type,
            series=series,
            correlativo=correlativo,
            client_doc_type=client_doc_type,
            client_doc_number=client_doc_number.strip(),
            client_name=client_name.strip() or "Público en general",
            client_address=client_address.strip(),
            items=line_items,
            subtotal=subtotal,
            igv=igv,
            total=total,
            currency=currency,
            issued_at=issued_at or datetime.now(timezone.utc),
            sale_id=sale_id,
        )
        return InvoiceDTO.from_entity(self._invoices.add(invoice))


class ListInvoices:
    def __init__(self, invoices: InvoiceRepository) -> None:
        self._invoices = invoices

    def execute(self, company_id: UUID) -> list[InvoiceDTO]:
        return [InvoiceDTO.from_entity(i) for i in self._invoices.list_by_company(company_id)]


class GetInvoice:
    def __init__(self, invoices: InvoiceRepository) -> None:
        self._invoices = invoices

    def execute(self, company_id: UUID, invoice_id: UUID) -> InvoiceDTO:
        invoice = self._invoices.get_by_id(invoice_id)
        if invoice is None or invoice.company_id != company_id:
            raise InvoiceNotFoundError(invoice_id)
        return InvoiceDTO.from_entity(invoice)


class VoidInvoice:
    def __init__(self, invoices: InvoiceRepository) -> None:
        self._invoices = invoices

    def execute(self, company_id: UUID, invoice_id: UUID) -> InvoiceDTO:
        invoice = self._invoices.get_by_id(invoice_id)
        if invoice is None or invoice.company_id != company_id:
            raise InvoiceNotFoundError(invoice_id)
        invoice.void()
        return InvoiceDTO.from_entity(self._invoices.update(invoice))
