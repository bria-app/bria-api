"""Ingestion module — HTTP router wired to use cases.

Implemented: upload a file (multipart, stored via StoragePort), list/get uploads,
set column mapping, mark validated. Preview/confirm/cancel and template endpoints
remain placeholders.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile

from app.modules.ingestion.application.dtos import IngestionBatchDTO
from app.modules.ingestion.application.use_cases.ingestion import (
    GetUpload,
    ListUploads,
    SetColumnMapping,
    UploadDataset,
    ValidateUpload,
)
from app.modules.ingestion.domain.repositories import IngestionBatchRepository
from app.modules.ingestion.presentation.dependencies import (
    get_ingestion_repository,
    get_storage,
)
from app.modules.ingestion.presentation.schemas import ColumnMappingRequest
from app.modules.files.domain.repositories import StoredFileRepository
from app.modules.files.presentation.dependencies import get_stored_file_repository
from app.shared.application.ports import StoragePort
from app.shared.presentation.deps import AuthenticatedUser, require_company_access
from app.shared.presentation.schemas import PlaceholderResponse

router = APIRouter()


@router.post("/uploads", response_model=IngestionBatchDTO, status_code=201)
async def create_upload(
    company_id: UUID,
    file: UploadFile = File(...),
    _: AuthenticatedUser = Depends(require_company_access),
    repo: IngestionBatchRepository = Depends(get_ingestion_repository),
    storage: StoragePort = Depends(get_storage),
    files: StoredFileRepository = Depends(get_stored_file_repository),
) -> IngestionBatchDTO:
    content = await file.read()
    return UploadDataset(repo, storage, files).execute(
        company_id,
        file_name=file.filename or "upload",
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )


@router.get("/uploads", response_model=list[IngestionBatchDTO])
def list_uploads(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: IngestionBatchRepository = Depends(get_ingestion_repository),
) -> list[IngestionBatchDTO]:
    return ListUploads(repo).execute(company_id)


@router.get("/uploads/{upload_id}", response_model=IngestionBatchDTO)
def get_upload(
    company_id: UUID,
    upload_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: IngestionBatchRepository = Depends(get_ingestion_repository),
) -> IngestionBatchDTO:
    return GetUpload(repo).execute(company_id, upload_id)


@router.post("/uploads/{upload_id}/mapping", response_model=IngestionBatchDTO)
def set_mapping(
    company_id: UUID,
    upload_id: UUID,
    request: ColumnMappingRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: IngestionBatchRepository = Depends(get_ingestion_repository),
) -> IngestionBatchDTO:
    return SetColumnMapping(repo).execute(company_id, upload_id, mapping=request.mapping)


@router.post("/uploads/{upload_id}/validate", response_model=IngestionBatchDTO)
def validate_upload(
    company_id: UUID,
    upload_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: IngestionBatchRepository = Depends(get_ingestion_repository),
) -> IngestionBatchDTO:
    return ValidateUpload(repo).execute(company_id, upload_id)


@router.post("/uploads/{upload_id}/confirm", response_model=PlaceholderResponse)
def confirm_upload(company_id: UUID, upload_id: UUID) -> PlaceholderResponse:
    # TODO(data_preparation): trigger dataset preparation pipeline.
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="ingestion", action="confirm_upload"
    )
