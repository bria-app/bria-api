"""Reports module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class ReportType(StrEnum):
    FORECAST = "forecast"
    KPI = "kpi"
    RECOMMENDATION = "recommendation"


class ReportStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
