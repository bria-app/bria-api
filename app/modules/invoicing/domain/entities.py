"""Invoicing module domain — entities.

Models a Peru-style comprobante de pago (Boleta de Venta / Factura): 18% IGV,
a series + correlativo per document type, and the DNI-vs-RUC rule that decides
which document a client can receive. This does not submit to SUNAT — issuing a
real electronic comprobante needs a digital certificate and UBL 2.1 XML
exchange with a PSE/OSE, which is out of scope for this academic prototype.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.invoicing.domain.enums import ClientDocType, DocumentType, InvoiceStatus
from app.modules.invoicing.domain.exceptions import InvalidInvoiceError


@dataclass(frozen=True)
class InvoiceItem:
    description: str
    quantity: int
    unit_price: Decimal
    product_id: UUID | None = None
    discount: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise InvalidInvoiceError(message="La cantidad de cada ítem debe ser mayor a cero")
        if self.discount < 0 or self.discount > self.unit_price * self.quantity:
            raise InvalidInvoiceError(message="El descuento del ítem no es válido")

    @property
    def subtotal(self) -> Decimal:
        """Line amount (quantity x unit price - discount)."""
        return (self.unit_price * self.quantity - self.discount).quantize(Decimal("0.01"))


@dataclass
class Invoice:
    company_id: UUID
    document_type: DocumentType
    series: str
    correlativo: int
    client_doc_type: ClientDocType
    client_doc_number: str
    client_name: str
    items: list[InvoiceItem]
    subtotal: Decimal
    igv: Decimal
    total: Decimal
    issued_at: datetime
    currency: str = "PEN"
    status: InvoiceStatus = InvoiceStatus.EMITIDA
    sale_id: UUID | None = None
    client_address: str = ""
    id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.items:
            raise InvalidInvoiceError(message="Un comprobante necesita al menos un ítem")
        if self.document_type == DocumentType.FACTURA and self.client_doc_type != ClientDocType.RUC:
            raise InvalidInvoiceError(message="Una Factura requiere RUC del cliente")
        if self.client_doc_type == ClientDocType.RUC and len(self.client_doc_number) != 11:
            raise InvalidInvoiceError(message="El RUC debe tener 11 dígitos")
        if self.client_doc_type == ClientDocType.DNI and len(self.client_doc_number) != 8:
            raise InvalidInvoiceError(message="El DNI debe tener 8 dígitos")

    @property
    def document_number(self) -> str:
        return f"{self.series}-{self.correlativo:08d}"

    def void(self) -> None:
        if self.status == InvoiceStatus.ANULADA:
            raise InvalidInvoiceError(message="El comprobante ya está anulado")
        self.status = InvoiceStatus.ANULADA
