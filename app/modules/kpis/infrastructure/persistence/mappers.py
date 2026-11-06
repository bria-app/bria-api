"""KPIs module — mappers."""
from __future__ import annotations

from app.modules.kpis.domain.entities import Kpi
from app.modules.kpis.domain.enums import KpiType
from app.modules.kpis.infrastructure.persistence.models import KpiModel


def kpi_to_entity(model: KpiModel) -> Kpi:
    return Kpi(
        id=model.id,
        company_id=model.company_id,
        product_id=model.product_id,
        kpi_type=KpiType(model.kpi_type),
        value=model.value,
        computed_at=model.computed_at,
        run_id=model.run_id,
    )


def kpi_to_model(entity: Kpi) -> KpiModel:
    return KpiModel(
        id=entity.id,
        company_id=entity.company_id,
        product_id=entity.product_id,
        kpi_type=entity.kpi_type.value,
        value=entity.value,
        computed_at=entity.computed_at,
        run_id=entity.run_id,
    )
