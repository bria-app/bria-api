"""KPIs module domain — exceptions."""
from __future__ import annotations

from app.shared.domain.errors import NotFoundError


class KpiNotFoundError(NotFoundError):
    pass
