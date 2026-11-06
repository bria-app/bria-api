"""Recommendations module domain — exceptions."""
from __future__ import annotations

from app.shared.domain.errors import ConflictError, NotFoundError, ValidationError


class RecommendationNotFoundError(NotFoundError):
    pass


class InvalidRecommendationError(ValidationError):
    pass


class RecommendationConflictError(ConflictError):
    """The recommendation is no longer pending (dismissed or replaced by a newer forecast)."""
