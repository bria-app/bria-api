"""Files module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules.files.domain.enums import FileCategory


@dataclass
class StoredFile:
    """A file stored on behalf of a company."""

    company_id: UUID
    file_name: str
    file_path: str
    content_type: str
    size_bytes: int
    category: FileCategory
    id: UUID | None = None
