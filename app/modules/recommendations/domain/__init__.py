"""Recommendations module — domain layer public API."""
from app.modules.recommendations.domain.entities import Recommendation
from app.modules.recommendations.domain.enums import (
    RecommendationPriority,
    RecommendationStatus,
)
from app.modules.recommendations.domain.exceptions import (
    InvalidRecommendationError,
    RecommendationConflictError,
    RecommendationNotFoundError,
)
from app.modules.recommendations.domain.repositories import RecommendationRepository

__all__ = [
    "InvalidRecommendationError",
    "Recommendation",
    "RecommendationConflictError",
    "RecommendationNotFoundError",
    "RecommendationPriority",
    "RecommendationRepository",
    "RecommendationStatus",
]
