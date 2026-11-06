"""KPIs module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class KpiType(StrEnum):
    COVERAGE_DAYS = "coverage_days"
    STOCKOUT_RISK = "stockout_risk"
    TURNOVER = "turnover"
    OVERSTOCK_RISK = "overstock_risk"
