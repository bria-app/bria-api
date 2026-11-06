"""Files module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.files.domain.entities import StoredFile


class StoredFileRepository(Protocol):
    """Port for StoredFile persistence."""

    def get_by_id(self, file_id: UUID) -> StoredFile | None: ...
    def list_by_company(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[StoredFile]: ...
    def add(self, stored_file: StoredFile) -> StoredFile: ...
    def delete(self, file_id: UUID) -> bool: ...
