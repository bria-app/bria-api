"""Recommendations module — presentation DI providers and enum parser."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.forecasting.infrastructure.persistence.repositories import (
    SqlForecastResultRepository,
    SqlForecastRunRepository,
)
from app.modules.inventory.infrastructure.persistence.repositories import (
    SqlInventoryMovementRepository,
)
from app.modules.products.infrastructure.persistence.repositories import (
    SqlProductRepository,
)
from app.modules.recommendations.domain.enums import RecommendationPriority
from app.modules.recommendations.infrastructure.persistence.repositories import (
    SqlRecommendationRepository,
)
from app.shared.domain.errors import ValidationError
from app.shared.infrastructure.database import get_db


def get_recommendation_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(db)


def get_product_repository(db: Session = Depends(get_db, scope="function")) -> SqlProductRepository:
    return SqlProductRepository(db)


def get_run_repository(db: Session = Depends(get_db, scope="function")) -> SqlForecastRunRepository:
    return SqlForecastRunRepository(db)


def get_result_repository(db: Session = Depends(get_db, scope="function")) -> SqlForecastResultRepository:
    return SqlForecastResultRepository(db)


def get_movement_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlInventoryMovementRepository:
    return SqlInventoryMovementRepository(db)


def parse_priority(value: str) -> RecommendationPriority:
    try:
        return RecommendationPriority(value)
    except ValueError as exc:
        valid = ", ".join(p.value for p in RecommendationPriority)
        raise ValidationError(
            message=f"La prioridad «{value}» no existe. Elige una de: {valid}."
        ) from exc
