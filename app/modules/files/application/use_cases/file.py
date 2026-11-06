"""Files module — application use cases."""
from __future__ import annotations

from uuid import UUID

from app.modules.files.application.dtos import FileDTO
from app.modules.files.domain.entities import StoredFile
from app.modules.files.domain.enums import FileCategory
from app.modules.files.domain.exceptions import StoredFileNotFoundError
from app.modules.files.domain.repositories import StoredFileRepository
from app.shared.application.ports import StoragePort


class UploadFile:
    def __init__(self, file_repo: StoredFileRepository, storage: StoragePort) -> None:
        self._file_repo = file_repo
        self._storage = storage

    def execute(
        self,
        company_id: UUID,
        file_name: str,
        content: bytes,
        content_type: str,
        category: FileCategory,
    ) -> FileDTO:
        # 1. Save bytes to storage
        storage_path = self._storage.save(file_name, content, content_type)

        # 2. Persist metadata
        entity = StoredFile(
            company_id=company_id,
            file_name=file_name,
            file_path=storage_path,
            content_type=content_type,
            size_bytes=len(content),
            category=category,
        )
        saved = self._file_repo.add(entity)
        return FileDTO.from_entity(saved)


class ListFiles:
    def __init__(self, file_repo: StoredFileRepository) -> None:
        self._file_repo = file_repo

    def execute(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[FileDTO]:
        entities = self._file_repo.list_by_company(
            company_id=company_id, offset=offset, limit=limit
        )
        return [FileDTO.from_entity(e) for e in entities]


class GetFile:
    """Returns metadata for a file."""

    def __init__(self, file_repo: StoredFileRepository) -> None:
        self._file_repo = file_repo

    def execute(self, company_id: UUID, file_id: UUID) -> FileDTO:
        entity = self._file_repo.get_by_id(file_id)
        if not entity or entity.company_id != company_id:
            raise StoredFileNotFoundError(file_id)
        return FileDTO.from_entity(entity)


class DownloadFile:
    """Returns the actual bytes (and content_type/filename) for a file."""

    def __init__(self, file_repo: StoredFileRepository, storage: StoragePort) -> None:
        self._file_repo = file_repo
        self._storage = storage

    def execute(self, company_id: UUID, file_id: UUID) -> tuple[bytes, str, str]:
        entity = self._file_repo.get_by_id(file_id)
        if not entity or entity.company_id != company_id:
            raise StoredFileNotFoundError(file_id)

        content = self._storage.get(entity.file_path)
        return content, entity.file_name, entity.content_type


class DeleteFile:
    def __init__(self, file_repo: StoredFileRepository, storage: StoragePort) -> None:
        self._file_repo = file_repo
        self._storage = storage

    def execute(self, company_id: UUID, file_id: UUID) -> None:
        entity = self._file_repo.get_by_id(file_id)
        if not entity or entity.company_id != company_id:
            raise StoredFileNotFoundError(file_id)

        # Remove from storage
        self._storage.delete(entity.file_path)

        # Remove from DB
        self._file_repo.delete(file_id)
