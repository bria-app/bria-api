"""Recommendations module — mappers."""
from __future__ import annotations

from app.modules.recommendations.domain.entities import Recommendation
from app.modules.recommendations.domain.enums import (
    RecommendationPriority,
    RecommendationStatus,
)
from app.modules.recommendations.infrastructure.persistence.models import (
    RecommendationModel,
)
from app.shared.domain.value_objects import Quantity


def recommendation_to_entity(model: RecommendationModel) -> Recommendation:
    return Recommendation(
        id=model.id,
        company_id=model.company_id,
        product_id=model.product_id,
        recommended_quantity=Quantity(model.recommended_quantity),
        priority=RecommendationPriority(model.priority),
        reason=model.reason,
        status=RecommendationStatus(model.status),
    )


def recommendation_to_model(entity: Recommendation) -> RecommendationModel:
    return RecommendationModel(
        id=entity.id,
        company_id=entity.company_id,
        product_id=entity.product_id,
        recommended_quantity=entity.recommended_quantity.value,
        priority=entity.priority.value,
        reason=entity.reason,
        status=entity.status.value,
    )
