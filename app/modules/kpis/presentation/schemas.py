"""KPIs module — presentation request schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class RecordKpiRequest(BaseModel):
    product_id: UUID
    kpi_type: str
    value: Decimal
    run_id: UUID | None = None
    computed_at: datetime | None = None
