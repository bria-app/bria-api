"""Files module — HTTP schemas."""
from __future__ import annotations


from app.modules.files.application.dtos import FileDTO


class FileResponse(FileDTO):
    """Response schema for a file's metadata."""
    pass


class FileMetadataResponse(FileDTO):
    """Response schema for a file's metadata (alias)."""
    pass
