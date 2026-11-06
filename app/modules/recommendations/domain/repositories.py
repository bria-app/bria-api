"""Recommendations module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.recommendations.domain.entities import Recommendation


class RecommendationRepository(Protocol):
    """Port for Recommendation persistence."""

    def get_by_id(self, recommendation_id: UUID) -> Recommendation | None: ...
    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Recommendation]: ...
    def list_pending(self, company_id: UUID) -> list[Recommendation]: ...
    def add(self, recommendation: Recommendation) -> Recommendation: ...
    def update(self, recommendation: Recommendation) -> Recommendation: ...
