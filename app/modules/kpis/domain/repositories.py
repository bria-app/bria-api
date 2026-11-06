"""KPIs module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.kpis.domain.entities import Kpi


class KpiRepository(Protocol):
    """Port for Kpi persistence."""

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Kpi]: ...
    def list_by_product(self, company_id: UUID, product_id: UUID) -> list[Kpi]: ...
    def add(self, kpi: Kpi) -> Kpi: ...
    def add_bulk(self, kpis: list[Kpi]) -> list[Kpi]: ...
