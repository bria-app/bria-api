"""Ingestion module — use cases.

Covers uploading a file (stored via StoragePort), registering its IngestionBatch,
setting the column mapping, and marking it validated. The analytical parsing/cleaning
of the file belongs to the data_preparation module.
"""
from __future__ import annotations

from uuid import UUID

from app.modules.ingestion.application.dtos import IngestionBatchDTO
from app.modules.ingestion.domain.entities import IngestionBatch
from app.modules.ingestion.domain.enums import FileType, IngestionStatus
from app.modules.ingestion.domain.exceptions import (
    IngestionBatchNotFoundError,
    InvalidIngestionError,
)
from app.modules.ingestion.domain.repositories import IngestionBatchRepository
from app.modules.files.domain.entities import StoredFile
from app.modules.files.domain.enums import FileCategory
from app.modules.files.domain.repositories import StoredFileRepository
from app.shared.application.ports import StoragePort


def _infer_file_type(file_name: str) -> FileType:
    ext = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
    if ext == "csv":
        return FileType.CSV
    if ext in ("xls", "xlsx"):
        return FileType.EXCEL
    raise InvalidIngestionError(
        message=f"No aceptamos archivos «{ext}». Sube un CSV, XLS o XLSX."
    )


class UploadDataset:
    def __init__(
        self,
        batches: IngestionBatchRepository,
        storage: StoragePort,
        files: StoredFileRepository | None = None,
    ) -> None:
        self._batches = batches
        self._storage = storage
        self._files = files

    def execute(
        self,
        company_id: UUID,
        *,
        file_name: str,
        content: bytes,
        content_type: str,
    ) -> IngestionBatchDTO:
        file_type = _infer_file_type(file_name)
        stored_path = self._storage.save(file_name, content, content_type)
        batch = IngestionBatch(
            company_id=company_id,
            file_name=file_name,
            file_path=stored_path,
            file_type=file_type,
        )
        result = IngestionBatchDTO.from_entity(self._batches.add(batch))

        # Also register the upload in the Files catalog so it shows under "Archivos"
        # (both point at the same stored blob — no duplicate storage).
        if self._files is not None:
            self._files.add(
                StoredFile(
                    company_id=company_id,
                    file_name=file_name,
                    file_path=stored_path,
                    content_type=content_type or "text/csv",
                    size_bytes=len(content),
                    category=FileCategory.ORIGINAL,
                )
            )
        return result


class ListUploads:
    def __init__(self, batches: IngestionBatchRepository) -> None:
        self._batches = batches

    def execute(self, company_id: UUID) -> list[IngestionBatchDTO]:
        return [
            IngestionBatchDTO.from_entity(b)
            for b in self._batches.list_by_company(company_id)
        ]


class GetUpload:
    def __init__(self, batches: IngestionBatchRepository) -> None:
        self._batches = batches

    def execute(self, company_id: UUID, batch_id: UUID) -> IngestionBatchDTO:
        batch = self._batches.get_by_id(batch_id)
        if batch is None or batch.company_id != company_id:
            raise IngestionBatchNotFoundError(
                message="No encontramos esa carga de archivo. Actualiza la página e inténtalo de nuevo."
            )
        return IngestionBatchDTO.from_entity(batch)


class SetColumnMapping:
    def __init__(self, batches: IngestionBatchRepository) -> None:
        self._batches = batches

    def execute(
        self, company_id: UUID, batch_id: UUID, *, mapping: dict[str, str]
    ) -> IngestionBatchDTO:
        batch = self._batches.get_by_id(batch_id)
        if batch is None or batch.company_id != company_id:
            raise IngestionBatchNotFoundError(
                message="No encontramos esa carga de archivo. Actualiza la página e inténtalo de nuevo."
            )
        batch.column_mapping = mapping
        batch.status = IngestionStatus.MAPPING
        return IngestionBatchDTO.from_entity(self._batches.update(batch))


class ValidateUpload:
    def __init__(self, batches: IngestionBatchRepository) -> None:
        self._batches = batches

    def execute(self, company_id: UUID, batch_id: UUID) -> IngestionBatchDTO:
        batch = self._batches.get_by_id(batch_id)
        if batch is None or batch.company_id != company_id:
            raise IngestionBatchNotFoundError(
                message="No encontramos esa carga de archivo. Actualiza la página e inténtalo de nuevo."
            )
        batch.mark_validated()
        return IngestionBatchDTO.from_entity(self._batches.update(batch))
