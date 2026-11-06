"""Recommendations module — presentation request schemas."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class CreateRecommendationRequest(BaseModel):
    product_id: UUID
    recommended_quantity: int
    priority: str = "medium"
    reason: str = ""
