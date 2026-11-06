"""Recommendations module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class RecommendationPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecommendationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    # Replaced by a newer forecast before anyone acted on it.
    SUPERSEDED = "superseded"
