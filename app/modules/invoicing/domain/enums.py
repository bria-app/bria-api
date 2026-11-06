"""Invoicing module domain — enums, Peru SUNAT conventions."""
from __future__ import annotations

from enum import StrEnum


class DocumentType(StrEnum):
    BOLETA = "boleta"
    FACTURA = "factura"


class ClientDocType(StrEnum):
    DNI = "dni"
    RUC = "ruc"
    NONE = "none"  # "Público en general" — allowed only on a boleta


class InvoiceStatus(StrEnum):
    EMITIDA = "emitida"
    ANULADA = "anulada"


# One default series per document type — real SUNAT setups can have several
# (one per point of sale); a single default per company keeps this prototype simple.
DEFAULT_SERIES = {
    DocumentType.BOLETA: "B001",
    DocumentType.FACTURA: "F001",
}
