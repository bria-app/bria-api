"""Suppliers module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import ConflictError, NotFoundError, ValidationError


class SupplierNotFoundError(NotFoundError):
    def __init__(self, supplier_id: UUID) -> None:
        super().__init__(
            message="No encontramos ese proveedor. Actualiza la página e inténtalo de nuevo.",
            details={"supplier_id": str(supplier_id)},
        )


class InvalidSupplierError(ValidationError):
    pass


class DuplicateSupplierError(ConflictError):
    def __init__(self, ruc: str) -> None:
        super().__init__(
            message=f"Ya existe un proveedor con el RUC {ruc}",
            details={"ruc": ruc},
        )
