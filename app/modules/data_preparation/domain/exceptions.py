"""Data preparation module domain — exceptions."""
from __future__ import annotations

from app.shared.domain.errors import NotFoundError, ValidationError


class PreparedDatasetNotFoundError(NotFoundError):
    pass


class InvalidDatasetError(ValidationError):
    pass
