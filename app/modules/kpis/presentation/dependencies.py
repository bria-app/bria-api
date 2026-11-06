"""KPIs module — presentation DI providers and enum parser."""
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
from app.modules.kpis.domain.enums import KpiType
from app.modules.kpis.infrastructure.persistence.repositories import SqlKpiRepository
from app.modules.products.infrastructure.persistence.repositories import (
    SqlProductRepository,
)
from app.shared.domain.errors import ValidationError
from app.shared.infrastructure.database import get_db


def get_kpi_repository(db: Session = Depends(get_db, scope="function")) -> SqlKpiRepository:
    return SqlKpiRepository(db)


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


def parse_kpi_type(value: str) -> KpiType:
    try:
        return KpiType(value)
    except ValueError as exc:
        valid = ", ".join(t.value for t in KpiType)
        raise ValidationError(
            message=f"El indicador «{value}» no existe. Elige uno de: {valid}."
        ) from exc
