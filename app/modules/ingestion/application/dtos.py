"""Ingestion module — application output DTOs."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.modules.ingestion.domain.entities import IngestionBatch


class IngestionBatchDTO(BaseModel):
    id: UUID
    company_id: UUID
    file_name: str
    file_path: str
    file_type: str
    column_mapping: dict[str, str]
    status: str
    row_count: int
    error_count: int

    @classmethod
    def from_entity(cls, batch: IngestionBatch) -> IngestionBatchDTO:
        assert batch.id is not None
        return cls(
            id=batch.id,
            company_id=batch.company_id,
            file_name=batch.file_name,
            file_path=batch.file_path,
            file_type=batch.file_type.value,
            column_mapping=batch.column_mapping,
            status=batch.status.value,
            row_count=batch.row_count,
            error_count=batch.error_count,
        )
