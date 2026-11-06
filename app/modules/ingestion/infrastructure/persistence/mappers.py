"""Ingestion module — mappers."""
from __future__ import annotations

from app.modules.ingestion.domain.entities import IngestionBatch
from app.modules.ingestion.domain.enums import FileType, IngestionStatus
from app.modules.ingestion.infrastructure.persistence.models import (
    IngestionBatchModel,
)


def batch_to_entity(model: IngestionBatchModel) -> IngestionBatch:
    return IngestionBatch(
        id=model.id,
        company_id=model.company_id,
        file_name=model.file_name,
        file_path=model.file_path,
        file_type=FileType(model.file_type),
        column_mapping=dict(model.column_mapping),
        status=IngestionStatus(model.status),
        row_count=model.row_count,
        error_count=model.error_count,
    )


def batch_to_model(entity: IngestionBatch) -> IngestionBatchModel:
    return IngestionBatchModel(
        id=entity.id,
        company_id=entity.company_id,
        file_name=entity.file_name,
        file_path=entity.file_path,
        file_type=entity.file_type.value,
        column_mapping=dict(entity.column_mapping),
        status=entity.status.value,
        row_count=entity.row_count,
        error_count=entity.error_count,
    )
