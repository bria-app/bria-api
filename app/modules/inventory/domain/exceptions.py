"""Inventory module domain — exceptions."""
from __future__ import annotations

from app.shared.domain.errors import NotFoundError, ValidationError


class InventoryMovementNotFoundError(NotFoundError):
    pass


class StockSnapshotNotFoundError(NotFoundError):
    pass


class ReplenishmentNotFoundError(NotFoundError):
    pass


class StockoutEventNotFoundError(NotFoundError):
    pass


class InvalidInventoryError(ValidationError):
    pass
