"""Invoicing module domain — pure services.

Peru's general sales tax (IGV) is 18%. A comprobante always prints the breakdown
Op. gravada (subtotal) + IGV = Total. Two ways to get there:

* prices WITHOUT IGV (B2B price lists): IGV is added on top of the lines.
* prices WITH IGV (retail shelf prices, the POS default): the lines already add up
  to the Total and the Op. gravada is extracted as Total / 1.18.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.modules.invoicing.domain.entities import InvoiceItem
from app.modules.invoicing.domain.enums import ClientDocType, DocumentType
from app.modules.invoicing.domain.exceptions import InvalidInvoiceError

IGV_RATE = Decimal("0.18")
CENT = Decimal("0.01")

# SUNAT: a boleta for S/ 700 or more must identify the buyer (DNI + name).
BOLETA_IDENTIFICATION_THRESHOLD = Decimal("700.00")

_RUC_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_RUC_PREFIXES = ("10", "15", "17", "20")


def split_igv_inclusive(total: Decimal) -> tuple[Decimal, Decimal]:
    """(op. gravada, igv) for a total that already includes IGV."""
    total = Decimal(total).quantize(CENT, rounding=ROUND_HALF_UP)
    subtotal = (total / (Decimal("1") + IGV_RATE)).quantize(CENT, rounding=ROUND_HALF_UP)
    return subtotal, total - subtotal


def compute_totals(
    items: list[InvoiceItem], prices_include_igv: bool = False
) -> tuple[Decimal, Decimal, Decimal]:
    """Returns (subtotal, igv, total) for a set of invoice items."""
    lines = sum((item.subtotal for item in items), Decimal("0.00"))
    if prices_include_igv:
        subtotal, igv = split_igv_inclusive(lines)
        return subtotal, igv, subtotal + igv
    igv = (lines * IGV_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
    return lines, igv, lines + igv


def is_valid_ruc(ruc: str) -> bool:
    """11 digits, a valid taxpayer prefix and a correct módulo-11 check digit."""
    if len(ruc) != 11 or not ruc.isdigit() or ruc[:2] not in _RUC_PREFIXES:
        return False
    total = sum(int(d) * w for d, w in zip(ruc[:10], _RUC_WEIGHTS))
    check = 11 - (total % 11)
    if check == 10:
        check = 0
    elif check == 11:
        check = 1
    return check == int(ruc[10])


def is_valid_dni(dni: str) -> bool:
    return len(dni) == 8 and dni.isdigit()


def validate_client(
    document_type: DocumentType,
    client_doc_type: ClientDocType,
    client_doc_number: str,
    client_name: str,
    total: Decimal,
) -> None:
    """SUNAT rules on who can receive which comprobante. Raises InvalidInvoiceError."""
    number = client_doc_number.strip()
    name = client_name.strip()
    if document_type == DocumentType.FACTURA:
        if client_doc_type != ClientDocType.RUC:
            raise InvalidInvoiceError(message="Una factura requiere el RUC del cliente.")
        if not is_valid_ruc(number):
            raise InvalidInvoiceError(
                message="El RUC no es válido: debe tener 11 dígitos, empezar con 10, 15, 17 o 20 y su dígito verificador debe ser correcto."
            )
        if not name:
            raise InvalidInvoiceError(message="Una factura requiere la razón social del cliente.")
        return

    # Boleta
    if client_doc_type == ClientDocType.RUC:
        raise InvalidInvoiceError(message="Para un cliente con RUC emite una factura.")
    if client_doc_type == ClientDocType.DNI and not is_valid_dni(number):
        raise InvalidInvoiceError(message="El DNI debe tener 8 dígitos.")
    if Decimal(total) >= BOLETA_IDENTIFICATION_THRESHOLD:
        if client_doc_type != ClientDocType.DNI or not name:
            raise InvalidInvoiceError(
                message="Boletas de S/ 700.00 o más requieren el DNI y el nombre del cliente (norma SUNAT)."
            )
