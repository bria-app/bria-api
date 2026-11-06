"""Sales module domain — exceptions."""
from __future__ import annotations

from typing import Any

from app.shared.domain.errors import ConflictError, NotFoundError, ValidationError


class SaleNotFoundError(NotFoundError):
    pass


class SalesBatchNotFoundError(NotFoundError):
    pass


class InvalidSaleError(ValidationError):
    pass


class SalesOrderNotFoundError(NotFoundError):
    pass


class InvalidSalesOrderError(ValidationError):
    pass


class ProductNotFoundForSaleError(NotFoundError):
    pass


class InsufficientStockError(ConflictError):
    """At least one cart line asks for more units than there are on hand."""

    def __init__(self, shortages: list[dict[str, Any]]) -> None:
        names = ", ".join(f"{s['name']} (disponible {s['available']})" for s in shortages)
        super().__init__(
            message=f"Stock insuficiente: {names}",
            details={"items": shortages},
        )
