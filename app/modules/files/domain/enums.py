"""Files module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class FileCategory(StrEnum):
    ORIGINAL = "original"
    DATASET = "dataset"
    REPORT = "report"
    OTHER = "other"
