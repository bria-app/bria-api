"""KPIs module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.kpis.domain.entities import Kpi
from app.modules.kpis.infrastructure.persistence.mappers import (
    kpi_to_entity,
    kpi_to_model,
)
from app.modules.kpis.infrastructure.persistence.models import KpiModel


class SqlKpiRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Kpi]:
        rows = self._session.execute(
            select(KpiModel)
            .where(KpiModel.company_id == company_id)
            .order_by(KpiModel.computed_at.desc())
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return [kpi_to_entity(m) for m in rows]

    def list_by_product(self, company_id: UUID, product_id: UUID) -> list[Kpi]:
        rows = self._session.execute(
            select(KpiModel)
            .where(KpiModel.company_id == company_id, KpiModel.product_id == product_id)
            .order_by(KpiModel.computed_at.desc())
        ).scalars().all()
        return [kpi_to_entity(m) for m in rows]

    def add(self, kpi: Kpi) -> Kpi:
        model = kpi_to_model(kpi)
        self._session.add(model)
        self._session.flush()
        return kpi_to_entity(model)

    def add_bulk(self, kpis: list[Kpi]) -> list[Kpi]:
        models = [kpi_to_model(k) for k in kpis]
        self._session.add_all(models)
        self._session.flush()
        return [kpi_to_entity(m) for m in models]
