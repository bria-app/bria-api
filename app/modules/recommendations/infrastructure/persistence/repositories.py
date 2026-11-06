"""Recommendations module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.recommendations.domain.entities import Recommendation
from app.modules.recommendations.domain.enums import RecommendationStatus
from app.modules.recommendations.domain.exceptions import RecommendationNotFoundError
from app.modules.recommendations.infrastructure.persistence.mappers import (
    recommendation_to_entity,
    recommendation_to_model,
)
from app.modules.recommendations.infrastructure.persistence.models import (
    RecommendationModel,
)


class SqlRecommendationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, recommendation_id: UUID) -> Recommendation | None:
        model = self._session.get(RecommendationModel, recommendation_id)
        return recommendation_to_entity(model) if model else None

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Recommendation]:
        rows = self._session.execute(
            select(RecommendationModel)
            .where(RecommendationModel.company_id == company_id)
            .order_by(RecommendationModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return [recommendation_to_entity(m) for m in rows]

    def list_pending(self, company_id: UUID) -> list[Recommendation]:
        rows = self._session.execute(
            select(RecommendationModel).where(
                RecommendationModel.company_id == company_id,
                RecommendationModel.status == RecommendationStatus.PENDING.value,
            )
        ).scalars().all()
        return [recommendation_to_entity(m) for m in rows]

    def add(self, recommendation: Recommendation) -> Recommendation:
        model = recommendation_to_model(recommendation)
        self._session.add(model)
        self._session.flush()
        return recommendation_to_entity(model)

    def update(self, recommendation: Recommendation) -> Recommendation:
        model = self._session.get(RecommendationModel, recommendation.id)
        if model is None:
            raise RecommendationNotFoundError(
                message="No encontramos esa recomendación. Actualiza la página e inténtalo de nuevo."
            )
        model.recommended_quantity = recommendation.recommended_quantity.value
        model.priority = recommendation.priority.value
        model.reason = recommendation.reason
        model.status = recommendation.status.value
        self._session.flush()
        return recommendation_to_entity(model)
