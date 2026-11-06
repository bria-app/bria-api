"""Validation module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class RuleType(StrEnum):
    MISSING_VALUE = "missing_value"
    OUTLIER = "outlier"
    FORMAT = "format"
