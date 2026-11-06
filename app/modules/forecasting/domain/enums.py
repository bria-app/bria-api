"""Forecasting module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    """Status of a forecast run.

    Kept as its own domain enum: the domain does not depend on infrastructure.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
