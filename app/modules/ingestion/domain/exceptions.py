"""Ingestion module domain — exceptions."""
from __future__ import annotations

from app.shared.domain.errors import NotFoundError, ValidationError


class IngestionBatchNotFoundError(NotFoundError):
    pass


class InvalidIngestionError(ValidationError):
    pass
