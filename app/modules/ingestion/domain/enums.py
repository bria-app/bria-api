"""Ingestion module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class IngestionStatus(StrEnum):
    UPLOADED = "uploaded"
    MAPPING = "mapping"
    VALIDATING = "validating"
    VALIDATED = "validated"
    FAILED = "failed"


class FileType(StrEnum):
    CSV = "csv"
    EXCEL = "excel"
