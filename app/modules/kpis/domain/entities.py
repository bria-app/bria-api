"""KPIs module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.kpis.domain.enums import KpiType


@dataclass
class Kpi:
    """A computed KPI value for a product at a point in time."""

    company_id: UUID
    product_id: UUID
    kpi_type: KpiType
    value: Decimal
    computed_at: datetime
    run_id: UUID | None = None
    id: UUID | None = None
