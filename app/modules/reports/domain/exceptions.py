"""Reports module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import NotFoundError, ValidationError


class ReportNotFoundError(NotFoundError):
    def __init__(self, report_id: UUID) -> None:
        super().__init__(
            message="No encontramos ese reporte. Actualiza la página e inténtalo de nuevo.",
            details={"report_id": str(report_id)},
        )


class InvalidReportStateError(ValidationError):
    pass
