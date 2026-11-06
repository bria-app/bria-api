"""Data preparation module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class DatasetStatus(StrEnum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    FAILED = "failed"
