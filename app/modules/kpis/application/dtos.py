"""KPIs module — application output DTOs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.modules.kpis.domain.entities import Kpi


class KpiDTO(BaseModel):
    id: UUID
    company_id: UUID
    product_id: UUID
    kpi_type: str
    value: Decimal
    computed_at: datetime
    run_id: UUID | None

    @classmethod
    def from_entity(cls, kpi: Kpi) -> KpiDTO:
        assert kpi.id is not None
        return cls(
            id=kpi.id,
            company_id=kpi.company_id,
            product_id=kpi.product_id,
            kpi_type=kpi.kpi_type.value,
            value=kpi.value,
            computed_at=kpi.computed_at,
            run_id=kpi.run_id,
        )
