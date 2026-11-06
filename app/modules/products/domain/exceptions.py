"""Products module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import ConflictError, NotFoundError, ValidationError


class CategoryNotFoundError(NotFoundError):
    def __init__(self, category_id: UUID) -> None:
        super().__init__(
            message="La categoría no existe.",
            details={"category_id": str(category_id)},
        )


class ProductNotFoundError(NotFoundError):
    def __init__(self, product_id: UUID) -> None:
        super().__init__(
            message="El producto no existe.",
            details={"product_id": str(product_id)},
        )


class ProductAlreadyExistsError(ConflictError):
    def __init__(self, sku: str) -> None:
        super().__init__(
            message=f"Ya existe un producto con el código '{sku}'.",
            details={"sku": sku},
        )


class BarcodeAlreadyExistsError(ConflictError):
    def __init__(self, barcode: str, product_name: str = "") -> None:
        suffix = f" ({product_name})" if product_name else ""
        super().__init__(
            message=f"El código de barras '{barcode}' ya está asignado a otro producto{suffix}.",
            details={"barcode": barcode},
        )


class InvalidProductError(ValidationError):
    pass


class ProductHasHistoryError(ConflictError):
    def __init__(self, product_id: UUID) -> None:
        super().__init__(
            message="Este producto tiene ventas o compras registradas: ponlo en pausa en lugar de borrarlo.",
            details={"product_id": str(product_id)},
        )


class CategoryInUseError(ConflictError):
    def __init__(self, category_id: UUID, subcategories: int, products: int) -> None:
        if subcategories:
            noun = "1 subcategoría" if subcategories == 1 else f"{subcategories} subcategorías"
            message = f"Esta categoría tiene {noun}: bórralas o muévelas antes de borrarla."
        else:
            noun = "1 producto" if products == 1 else f"{products} productos"
            message = (
                f"Esta categoría tiene {noun} (contando los pausados): "
                "muévelos a otra categoría antes de borrarla."
            )
        super().__init__(
            message=message,
            details={
                "category_id": str(category_id),
                "subcategories": subcategories,
                "products": products,
            },
        )
