"""Ingestion module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.modules.ingestion.domain.enums import FileType, IngestionStatus
from app.modules.ingestion.domain.exceptions import InvalidIngestionError


@dataclass
class IngestionBatch:
    """Tracks an uploaded file through the ingestion pipeline."""

    company_id: UUID
    file_name: str
    file_path: str
    file_type: FileType
    column_mapping: dict[str, str] = field(default_factory=dict)
    status: IngestionStatus = IngestionStatus.UPLOADED
    row_count: int = 0
    error_count: int = 0
    id: UUID | None = None

    def __post_init__(self) -> None:
        if self.row_count < 0:
            raise InvalidIngestionError(
                message=f"El número de filas no puede ser negativo ({self.row_count})."
            )
        if self.error_count < 0:
            raise InvalidIngestionError(
                message=f"El número de errores no puede ser negativo ({self.error_count})."
            )

    def mark_validated(self) -> None:
        """Transition to validated status."""
        if self.status not in (IngestionStatus.VALIDATING, IngestionStatus.MAPPING):
            raise InvalidIngestionError(
                message=f"Esta carga no se puede validar en estado «{self.status}». Sube el archivo de nuevo."
            )
        self.status = IngestionStatus.VALIDATED

    def mark_failed(self) -> None:
        """Transition to failed status."""
        self.status = IngestionStatus.FAILED
