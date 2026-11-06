"""Recommendations module — application output DTOs."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.modules.recommendations.domain.entities import Recommendation


class RecommendationDTO(BaseModel):
    id: UUID
    company_id: UUID
    product_id: UUID
    recommended_quantity: int
    priority: str
    reason: str
    status: str

    @classmethod
    def from_entity(cls, r: Recommendation) -> RecommendationDTO:
        assert r.id is not None
        return cls(
            id=r.id,
            company_id=r.company_id,
            product_id=r.product_id,
            recommended_quantity=r.recommended_quantity.value,
            priority=r.priority.value,
            reason=r.reason,
            status=r.status.value,
        )
