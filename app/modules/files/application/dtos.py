"""Files module — application DTOs."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.files.domain.entities import StoredFile
from app.modules.files.domain.enums import FileCategory


class FileDTO(BaseModel):
    id: UUID
    company_id: UUID
    file_name: str
    content_type: str
    size_bytes: int
    category: FileCategory

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, entity: StoredFile) -> FileDTO:
        if entity.id is None:
            raise ValueError("Entity must have an id to create DTO")
        return cls(
            id=entity.id,
            company_id=entity.company_id,
            file_name=entity.file_name,
            content_type=entity.content_type,
            size_bytes=entity.size_bytes,
            category=entity.category,
        )
