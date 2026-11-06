"""Forecasting module domain — exceptions."""
from __future__ import annotations

from app.shared.domain.errors import NotFoundError, ValidationError


class ForecastRunNotFoundError(NotFoundError):
    pass


class ForecastResultNotFoundError(NotFoundError):
    pass


class InvalidRunTransitionError(ValidationError):
    pass
