"""Notifications module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
