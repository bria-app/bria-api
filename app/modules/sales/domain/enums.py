"""Sales module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class BatchStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class SalesDocumentType(StrEnum):
    """Comprobante handed to the client at the till."""

    BOLETA = "boleta"
    FACTURA = "factura"
    NOTA_VENTA = "nota_venta"  # internal ticket, no SUNAT comprobante


class ClientDocType(StrEnum):
    DNI = "dni"
    RUC = "ruc"
    NONE = "none"


class PaymentMethod(StrEnum):
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    YAPE = "yape"
    PLIN = "plin"
    TRANSFERENCIA = "transferencia"


class OrderStatus(StrEnum):
    COMPLETED = "completed"
    VOIDED = "voided"
