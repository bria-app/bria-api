"""Dashboard module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class WidgetType(StrEnum):
    KPI_CARD = "kpi_card"
    CHART = "chart"
    TABLE = "table"
    ALERT = "alert"
