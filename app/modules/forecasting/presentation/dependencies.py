"""Forecasting module — presentation DI providers."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.data_preparation.infrastructure.erp_source import ErpDataSource
from app.modules.data_preparation.infrastructure.persistence.repositories import (
    SqlPreparedDatasetRepository,
)
from app.modules.forecasting.infrastructure.persistence.repositories import (
    SqlForecastMetricsRepository,
    SqlForecastResultRepository,
    SqlForecastRunRepository,
)
from app.modules.recommendations.infrastructure.persistence.repositories import (
    SqlRecommendationRepository,
)
from app.shared.infrastructure.database import get_db


def get_session(db: Session = Depends(get_db, scope="function")) -> Session:
    return db


def get_run_repository(db: Session = Depends(get_db, scope="function")) -> SqlForecastRunRepository:
    return SqlForecastRunRepository(db)


def get_dataset_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlPreparedDatasetRepository:
    return SqlPreparedDatasetRepository(db)


def get_result_repository(db: Session = Depends(get_db, scope="function")) -> SqlForecastResultRepository:
    return SqlForecastResultRepository(db)


def get_metrics_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlForecastMetricsRepository:
    return SqlForecastMetricsRepository(db)


def get_erp_source(db: Session = Depends(get_db, scope="function")) -> ErpDataSource:
    return ErpDataSource(db)


def get_recommendation_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(db)
