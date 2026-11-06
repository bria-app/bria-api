"""Billing module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import NotFoundError, ValidationError


class SubscriptionNotFoundError(NotFoundError):
    def __init__(self, company_id: UUID) -> None:
        super().__init__(
            message="Tu empresa aún no tiene una suscripción. Elige un plan para empezar.",
            details={"company_id": str(company_id)},
        )


class PlanNotFoundError(NotFoundError):
    def __init__(self, plan_id: str) -> None:
        super().__init__(message=f"El plan «{plan_id}» no existe. Elige uno de la lista.", details={"plan_id": plan_id})


class PaymentValidationError(ValidationError):
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message=message, details={"field": field} if field else None)
