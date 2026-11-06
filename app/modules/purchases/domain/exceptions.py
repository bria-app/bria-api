"""Purchases module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import ConflictError, NotFoundError, ValidationError


class PurchaseDocumentNotFoundError(NotFoundError):
    def __init__(self, document_id: str) -> None:
        super().__init__(message="No encontramos ese documento de compra. Actualiza la página e inténtalo de nuevo.", details={"document_id": document_id})


class PurchaseSupplierNotFoundError(NotFoundError):
    def __init__(self, supplier_id: UUID) -> None:
        super().__init__(message="Ese proveedor ya no existe. Elige otro.", details={"supplier_id": str(supplier_id)})


class PurchaseProductNotFoundError(NotFoundError):
    def __init__(self, product_id: UUID) -> None:
        super().__init__(message="Ese producto ya no existe. Elige otro.", details={"product_id": str(product_id)})


class InvalidPurchaseError(ValidationError):
    pass


class FuturePurchaseDateError(InvalidPurchaseError):
    def __init__(self, purchase_date: object) -> None:
        super().__init__(
            message="La fecha de la compra no puede ser futura.",
            details={"purchase_date": str(purchase_date)},
        )


class DuplicateProductCodeError(ConflictError):
    def __init__(self, sku: str) -> None:
        super().__init__(message=f"Ya existe un producto con el código {sku}", details={"sku": sku})
