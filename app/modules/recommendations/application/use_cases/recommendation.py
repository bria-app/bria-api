"""Recommendations module — use cases.

Bloque 2 covers persistence and lifecycle (create/list/accept/dismiss). Automatic
generation of recommendations from KPIs + forecasts is a later block.
"""
from __future__ import annotations

from uuid import UUID

from app.modules.recommendations.application.dtos import RecommendationDTO
from app.modules.recommendations.domain.entities import Recommendation
from app.modules.recommendations.domain.enums import RecommendationPriority
from app.modules.recommendations.domain.exceptions import RecommendationNotFoundError
from app.modules.recommendations.domain.repositories import RecommendationRepository
from app.shared.domain.value_objects import Quantity


class CreateRecommendation:
    def __init__(self, recommendations: RecommendationRepository) -> None:
        self._recommendations = recommendations

    def execute(
        self,
        company_id: UUID,
        *,
        product_id: UUID,
        recommended_quantity: int,
        priority: RecommendationPriority,
        reason: str = "",
    ) -> RecommendationDTO:
        recommendation = Recommendation(
            company_id=company_id,
            product_id=product_id,
            recommended_quantity=Quantity(recommended_quantity),
            priority=priority,
            reason=reason,
        )
        return RecommendationDTO.from_entity(
            self._recommendations.add(recommendation)
        )


class GetRecommendation:
    def __init__(self, recommendations: RecommendationRepository) -> None:
        self._recommendations = recommendations

    def execute(self, company_id: UUID, recommendation_id: UUID) -> RecommendationDTO:
        recommendation = self._recommendations.get_by_id(recommendation_id)
        if recommendation is None or recommendation.company_id != company_id:
            raise RecommendationNotFoundError(
                message="No encontramos esa recomendación. Actualiza la página e inténtalo de nuevo."
            )
        return RecommendationDTO.from_entity(recommendation)


class ListRecommendations:
    def __init__(self, recommendations: RecommendationRepository) -> None:
        self._recommendations = recommendations

    def execute(
        self, company_id: UUID, *, pending_only: bool = False
    ) -> list[RecommendationDTO]:
        items = (
            self._recommendations.list_pending(company_id)
            if pending_only
            else self._recommendations.list_by_company(company_id)
        )
        return [RecommendationDTO.from_entity(r) for r in items]


class AcceptRecommendation:
    def __init__(self, recommendations: RecommendationRepository) -> None:
        self._recommendations = recommendations

    def execute(self, company_id: UUID, recommendation_id: UUID) -> RecommendationDTO:
        recommendation = self._recommendations.get_by_id(recommendation_id)
        if recommendation is None or recommendation.company_id != company_id:
            raise RecommendationNotFoundError(
                message="No encontramos esa recomendación. Actualiza la página e inténtalo de nuevo."
            )
        if not recommendation.accept():
            # Already accepted: return it unchanged (a repeated click must not fail).
            return RecommendationDTO.from_entity(recommendation)
        return RecommendationDTO.from_entity(
            self._recommendations.update(recommendation)
        )


class DismissRecommendation:
    def __init__(self, recommendations: RecommendationRepository) -> None:
        self._recommendations = recommendations

    def execute(self, company_id: UUID, recommendation_id: UUID) -> RecommendationDTO:
        recommendation = self._recommendations.get_by_id(recommendation_id)
        if recommendation is None or recommendation.company_id != company_id:
            raise RecommendationNotFoundError(
                message="No encontramos esa recomendación. Actualiza la página e inténtalo de nuevo."
            )
        recommendation.dismiss()
        return RecommendationDTO.from_entity(
            self._recommendations.update(recommendation)
        )
