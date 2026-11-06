"""Dashboard module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import NotFoundError


class DashboardWidgetNotFoundError(NotFoundError):
    def __init__(self, widget_id: UUID) -> None:
        super().__init__(
            message="No encontramos ese widget. Actualiza la página e inténtalo de nuevo.",
            details={"widget_id": str(widget_id)},
        )
