"""KPIs module — use cases.

Bloque 2 covers KPI persistence and querying. The automatic KPI computation
(coverage, stockout risk, turnover, overstock) is a cross-module orchestration over
forecasts + stock + product parameters and is implemented in a later block.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.modules.kpis.application.dtos import KpiDTO
from app.modules.kpis.domain.entities import Kpi
from app.modules.kpis.domain.enums import KpiType
from app.modules.kpis.domain.repositories import KpiRepository


class RecordKpi:
    def __init__(self, kpis: KpiRepository) -> None:
        self._kpis = kpis

    def execute(
        self,
        company_id: UUID,
        *,
        product_id: UUID,
        kpi_type: KpiType,
        value: Decimal,
        run_id: UUID | None = None,
        computed_at: datetime | None = None,
    ) -> KpiDTO:
        kpi = Kpi(
            company_id=company_id,
            product_id=product_id,
            kpi_type=kpi_type,
            value=value,
            computed_at=computed_at or datetime.now(timezone.utc),
            run_id=run_id,
        )
        return KpiDTO.from_entity(self._kpis.add(kpi))


class ListKpis:
    def __init__(self, kpis: KpiRepository) -> None:
        self._kpis = kpis

    def execute(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[KpiDTO]:
        return [
            KpiDTO.from_entity(k)
            for k in self._kpis.list_by_company(company_id, offset, limit)
        ]


class ListProductKpis:
    def __init__(self, kpis: KpiRepository) -> None:
        self._kpis = kpis

    def execute(self, company_id: UUID, product_id: UUID) -> list[KpiDTO]:
        return [
            KpiDTO.from_entity(k) for k in self._kpis.list_by_product(company_id, product_id)
        ]
