"""Sales module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.invoicing.domain.enums import ClientDocType as InvoiceClientDocType
from app.modules.invoicing.domain.enums import DocumentType as InvoiceDocumentType
from app.modules.invoicing.domain.services import (
    is_valid_dni,
    is_valid_ruc,
    split_igv_inclusive,
    validate_client,
)
from app.modules.sales.domain.enums import (
    BatchStatus,
    ClientDocType,
    OrderStatus,
    PaymentMethod,
    SalesDocumentType,
)
from app.modules.sales.domain.exceptions import InvalidSaleError, InvalidSalesOrderError
from app.shared.domain.value_objects import DateRange, Money, Quantity

CENT = Decimal("0.01")


@dataclass
class SalesBatch:
    """A batch of imported sales data."""

    company_id: UUID
    source_file: str
    status: BatchStatus = BatchStatus.PENDING
    row_count: int = 0
    period: DateRange | None = None
    id: UUID | None = None

    def __post_init__(self) -> None:
        if self.row_count < 0:
            raise InvalidSaleError(
                message=f"El número de filas no puede ser negativo ({self.row_count})."
            )


@dataclass
class Sale:
    """An individual sale transaction (one product line).

    Invariant: total_amount == unit_price * quantity. A POS line (order_id set) may
    carry a line discount, so there total_amount <= unit_price * quantity.
    """

    company_id: UUID
    product_id: UUID
    sale_date: date
    quantity: Quantity
    unit_price: Money
    total_amount: Money
    batch_id: UUID | None = None
    order_id: UUID | None = None
    seller_id: UUID | None = None
    seller_name: str = ""
    unit_cost: Decimal | None = None
    id: UUID | None = None
    # Read-only labels of the product (filled when the sale is read from storage).
    product_name: str = ""
    sku: str = ""

    def __post_init__(self) -> None:
        expected = self.unit_price.amount * Decimal(self.quantity.value)
        mismatch = (
            self.total_amount.amount > expected
            if self.order_id is not None
            else self.total_amount.amount != expected
        )
        if mismatch:
            raise InvalidSaleError(
                message=(
                    f"El total ({self.total_amount.amount}) no coincide con precio × cantidad "
                    f"({expected}). Revisa los importes."
                )
            )
        if self.unit_price.currency != self.total_amount.currency:
            raise InvalidSaleError(
                message=(
                    f"El precio está en {self.unit_price.currency} y el total en "
                    f"{self.total_amount.currency}. Usa una sola moneda."
                )
            )

    @property
    def discount(self) -> Decimal:
        return self.unit_price.amount * Decimal(self.quantity.value) - self.total_amount.amount


@dataclass(frozen=True)
class CatalogProduct:
    """Read-only view of a product as the till sees it (with stock on hand)."""

    id: UUID
    sku: str
    name: str
    unit_price: Decimal
    unit_cost: Decimal
    currency: str
    is_active: bool
    stock_on_hand: int
    description: str = ""
    barcode: str | None = None
    image_url: str | None = None
    unit_of_measure: str = "unit"
    category_id: UUID | None = None
    category_name: str | None = None
    reorder_point: int = 0
    safety_stock: int = 0
    custom_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SalesOrderLine:
    product_id: UUID
    quantity: int
    unit_price: Decimal
    discount: Decimal = Decimal("0")
    unit_cost: Decimal | None = None
    product_name: str = ""
    sku: str = ""
    id: UUID | None = None

    def __post_init__(self) -> None:
        label = self.product_name or str(self.product_id)
        if self.quantity <= 0:
            raise InvalidSalesOrderError(message=f"La cantidad de «{label}» debe ser mayor a cero")
        if self.unit_price < 0:
            raise InvalidSalesOrderError(message=f"El precio de «{label}» no puede ser negativo")
        if self.discount < 0 or self.discount > self.unit_price * self.quantity:
            raise InvalidSalesOrderError(
                message=f"El descuento de «{label}» no puede superar el importe de la línea"
            )

    @property
    def line_total(self) -> Decimal:
        return (self.unit_price * self.quantity - self.discount).quantize(CENT)


@dataclass
class SalesOrder:
    """A POS ticket. Retail prices include IGV: Total = Σ lines, Op. gravada = Total / 1.18."""

    company_id: UUID
    order_number: int
    document_type: SalesDocumentType
    client_doc_type: ClientDocType
    client_doc_number: str
    client_name: str
    payment_method: PaymentMethod
    lines: list[SalesOrderLine]
    sold_at: datetime
    seller_id: UUID | None = None
    seller_name: str = ""
    client_address: str = ""
    amount_received: Decimal | None = None
    notes: str = ""
    currency: str = "PEN"
    status: OrderStatus = OrderStatus.COMPLETED
    invoice_id: UUID | None = None
    id: UUID | None = None

    @property
    def total(self) -> Decimal:
        return sum((line.line_total for line in self.lines), Decimal("0.00"))

    @property
    def subtotal(self) -> Decimal:
        return split_igv_inclusive(self.total)[0]

    @property
    def igv(self) -> Decimal:
        return split_igv_inclusive(self.total)[1]

    @property
    def discount_total(self) -> Decimal:
        return sum((line.discount for line in self.lines), Decimal("0.00")).quantize(CENT)

    @property
    def change(self) -> Decimal | None:
        if self.payment_method != PaymentMethod.EFECTIVO or self.amount_received is None:
            return None
        return (self.amount_received - self.total).quantize(CENT)

    @property
    def issues_invoice(self) -> bool:
        return self.document_type in (SalesDocumentType.BOLETA, SalesDocumentType.FACTURA)

    def validate(self) -> None:
        """Business rules checked before the ticket is persisted."""
        if not self.lines:
            raise InvalidSalesOrderError(message="Agrega al menos un producto a la venta")
        self.client_doc_number = self.client_doc_number.strip()
        self.client_name = self.client_name.strip()
        self.client_address = self.client_address.strip()
        if self.client_doc_type == ClientDocType.NONE:
            self.client_doc_number = ""

        if self.issues_invoice:
            validate_client(
                InvoiceDocumentType(self.document_type.value),
                InvoiceClientDocType(self.client_doc_type.value),
                self.client_doc_number,
                self.client_name,
                self.total,
            )
        else:
            if self.client_doc_type == ClientDocType.DNI and not is_valid_dni(self.client_doc_number):
                raise InvalidSalesOrderError(message="El DNI debe tener 8 dígitos.")
            if self.client_doc_type == ClientDocType.RUC and not is_valid_ruc(self.client_doc_number):
                raise InvalidSalesOrderError(message="El RUC no es válido. Revisa que tenga 11 dígitos.")

        if self.payment_method == PaymentMethod.EFECTIVO:
            if self.amount_received is not None and self.amount_received < self.total:
                raise InvalidSalesOrderError(
                    message=f"El monto recibido (S/ {self.amount_received:.2f}) es menor al total (S/ {self.total:.2f})"
                )
        else:
            self.amount_received = None

    def void(self) -> None:
        if self.status == OrderStatus.VOIDED:
            raise InvalidSalesOrderError(message="Esta venta ya está anulada")
        self.status = OrderStatus.VOIDED


@dataclass
class LostSale:
    """A sale that could not happen for lack of stock (quiebre de stock)."""

    company_id: UUID
    product_id: UUID
    requested_quantity: int
    available_quantity: int
    occurred_at: datetime
    seller_id: UUID | None = None
    seller_name: str = ""
    source: str = "pos"
    id: UUID | None = None

    def __post_init__(self) -> None:
        if self.requested_quantity <= 0:
            raise InvalidSaleError(message="La cantidad solicitada debe ser mayor a cero")
        if self.available_quantity < 0:
            self.available_quantity = 0
