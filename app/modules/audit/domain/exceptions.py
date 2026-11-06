"""Audit module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import NotFoundError


class AuditEventNotFoundError(NotFoundError):
    def __init__(self, event_id: UUID) -> None:
        super().__init__(
            message="No encontramos ese evento de auditoría. Actualiza la página e inténtalo de nuevo.",
            details={"event_id": str(event_id)},
        )
