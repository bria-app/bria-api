"""Files module — HTTP router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile as FastAPIUploadFile, status
from fastapi.responses import Response

from app.modules.files.application.use_cases.file import (
    DeleteFile,
    DownloadFile,
    GetFile,
    ListFiles,
    UploadFile,
)
from app.modules.files.domain.enums import FileCategory
from app.modules.files.domain.repositories import StoredFileRepository
from app.modules.files.presentation.dependencies import (
    get_storage_port,
    get_stored_file_repository,
)
from app.modules.files.presentation.schemas import FileMetadataResponse, FileResponse
from app.shared.application.ports import StoragePort
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
)
from app.shared.presentation.schemas import (
    MessageResponse,
    PaginatedResponse,
    PaginationParams,
    PlaceholderResponse,
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[FileResponse])
def list_files(
    company_id: UUID,
    repo: Annotated[StoredFileRepository, Depends(get_stored_file_repository)],
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> PaginatedResponse[FileResponse]:
    use_case = ListFiles(repo)
    offset = (pagination.page - 1) * pagination.size
    dtos = use_case.execute(
        company_id=company_id,
        offset=offset,
        limit=pagination.size,
    )
    return PaginatedResponse(
        items=[FileResponse.model_validate(d) for d in dtos],
        total=len(dtos),
        page=pagination.page,
        size=pagination.size,
        pages=1,
    )


@router.post("", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def create_file(
    company_id: UUID,
    repo: Annotated[StoredFileRepository, Depends(get_stored_file_repository)],
    storage: Annotated[StoragePort, Depends(get_storage_port)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
    file: FastAPIUploadFile = File(...),
    category: FileCategory = Form(FileCategory.OTHER),
) -> FileResponse:
    content = await file.read()
    use_case = UploadFile(repo, storage)
    
    file_name = file.filename or "unknown_file"
    content_type = file.content_type or "application/octet-stream"

    dto = use_case.execute(
        company_id=company_id,
        file_name=file_name,
        content=content,
        content_type=content_type,
        category=category,
    )
    return FileResponse.model_validate(dto, from_attributes=True)


@router.get("/by-upload/{upload_id}", response_model=PlaceholderResponse)
def get_files_by_upload(company_id: UUID, upload_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="files", action="get_files_by_upload"
    )


@router.get("/by-report/{report_id}", response_model=PlaceholderResponse)
def get_files_by_report(company_id: UUID, report_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="files", action="get_files_by_report"
    )


@router.get("/{file_id}", response_model=FileResponse)
def get_file(
    company_id: UUID,
    file_id: UUID,
    repo: Annotated[StoredFileRepository, Depends(get_stored_file_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> FileResponse:
    use_case = GetFile(repo)
    dto = use_case.execute(company_id=company_id, file_id=file_id)
    return FileResponse.model_validate(dto, from_attributes=True)


@router.delete("/{file_id}", response_model=MessageResponse)
def delete_file(
    company_id: UUID,
    file_id: UUID,
    repo: Annotated[StoredFileRepository, Depends(get_stored_file_repository)],
    storage: Annotated[StoragePort, Depends(get_storage_port)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> MessageResponse:
    use_case = DeleteFile(repo, storage)
    use_case.execute(company_id=company_id, file_id=file_id)
    return MessageResponse(message="File deleted successfully")


@router.get("/{file_id}/download")
def download_file(
    company_id: UUID,
    file_id: UUID,
    repo: Annotated[StoredFileRepository, Depends(get_stored_file_repository)],
    storage: Annotated[StoragePort, Depends(get_storage_port)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> Response:
    use_case = DownloadFile(repo, storage)
    content, file_name, content_type = use_case.execute(
        company_id=company_id, file_id=file_id
    )
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/{file_id}/metadata", response_model=FileMetadataResponse)
def get_file_metadata(
    company_id: UUID,
    file_id: UUID,
    repo: Annotated[StoredFileRepository, Depends(get_stored_file_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> FileMetadataResponse:
    use_case = GetFile(repo)
    dto = use_case.execute(company_id=company_id, file_id=file_id)
    return FileMetadataResponse.model_validate(dto, from_attributes=True)


@router.post("/{file_id}/restore", response_model=PlaceholderResponse)
def restore_file(company_id: UUID, file_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="files", action="restore_file"
    )
