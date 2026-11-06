"""Files module — mappers."""
from __future__ import annotations

from app.modules.files.domain.entities import StoredFile
from app.modules.files.domain.enums import FileCategory
from app.modules.files.infrastructure.persistence.models import StoredFileModel


def stored_file_to_entity(model: StoredFileModel) -> StoredFile:
    return StoredFile(
        id=model.id,
        company_id=model.company_id,
        file_name=model.file_name,
        file_path=model.file_path,
        content_type=model.content_type,
        size_bytes=model.size_bytes,
        category=FileCategory(model.category),
    )


def stored_file_to_model(entity: StoredFile) -> StoredFileModel:
    return StoredFileModel(
        id=entity.id,
        company_id=entity.company_id,
        file_name=entity.file_name,
        file_path=entity.file_path,
        content_type=entity.content_type,
        size_bytes=entity.size_bytes,
        category=entity.category.value,
    )
