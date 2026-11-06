"""Recommendations module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules.recommendations.domain.enums import (
    RecommendationPriority,
    RecommendationStatus,
)
from app.modules.recommendations.domain.exceptions import (
    InvalidRecommendationError,
    RecommendationConflictError,
)
from app.shared.domain.value_objects import Quantity


@dataclass
class Recommendation:
    """An actionable replenishment recommendation for a product."""

    company_id: UUID
    product_id: UUID
    recommended_quantity: Quantity
    priority: RecommendationPriority
    reason: str
    status: RecommendationStatus = RecommendationStatus.PENDING
    id: UUID | None = None

    def accept(self) -> bool:
        """Accept this recommendation; True if it changed.

        Idempotent: accepting one already accepted (a double click, a retry) leaves it as is.
        One dismissed or replaced by a newer forecast can no longer be accepted.
        """
        if self.status == RecommendationStatus.ACCEPTED:
            return False
        if self.status == RecommendationStatus.DISMISSED:
            raise RecommendationConflictError(
                message="Esta sugerencia ya fue descartada, así que no se puede aceptar."
            )
        if self.status == RecommendationStatus.SUPERSEDED:
            raise RecommendationConflictError(
                message=(
                    "Esta sugerencia ya no está vigente: un pronóstico más nuevo la reemplazó. "
                    "Revisa «Qué comprar» otra vez."
                )
            )
        if self.status != RecommendationStatus.PENDING:
            raise RecommendationConflictError(
                message="Esta sugerencia ya no se puede aceptar. Actualiza la página."
            )
        self.status = RecommendationStatus.ACCEPTED
        return True

    def refresh(self, quantity: Quantity, priority: RecommendationPriority, reason: str) -> bool:
        """Bring a pending recommendation in line with a newer forecast; True if it changed."""
        if self.status != RecommendationStatus.PENDING:
            return False
        changed = (self.recommended_quantity, self.priority, self.reason) != (quantity, priority, reason)
        self.recommended_quantity, self.priority, self.reason = quantity, priority, reason
        return changed

    def supersede(self) -> None:
        """A newer forecast no longer asks for this purchase."""
        if self.status == RecommendationStatus.PENDING:
            self.status = RecommendationStatus.SUPERSEDED

    def dismiss(self) -> None:
        """Dismiss this recommendation."""
        if self.status != RecommendationStatus.PENDING:
            raise InvalidRecommendationError(
                message=f"Esta recomendación ya no se puede descartar (estado: {self.status})."
            )
        self.status = RecommendationStatus.DISMISSED
