"""Validation module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import NotFoundError


class ValidationRuleNotFoundError(NotFoundError):
    def __init__(self, rule_id: UUID) -> None:
        super().__init__(
            message="No encontramos esa regla de validación. Actualiza la página e inténtalo de nuevo.",
            details={"rule_id": str(rule_id)},
        )
