"""Invoicing module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import NotFoundError, ValidationError


class InvoiceNotFoundError(NotFoundError):
    def __init__(self, invoice_id: UUID) -> None:
        super().__init__(
            message="No encontramos ese comprobante. Actualiza la página e inténtalo de nuevo.",
            details={"invoice_id": str(invoice_id)},
        )


class InvalidInvoiceError(ValidationError):
    pass
