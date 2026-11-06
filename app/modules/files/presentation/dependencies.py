"""Files module — dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.files.domain.repositories import StoredFileRepository
from app.modules.files.infrastructure.persistence.repositories import (
    SqlStoredFileRepository,
)
from app.shared.application.ports import StoragePort
from app.shared.infrastructure.storage.factory import make_storage
from app.shared.presentation.deps import get_db


def get_stored_file_repository(
    db: Annotated[Session, Depends(get_db, scope="function")],
) -> StoredFileRepository:
    """Dependency provider for StoredFileRepository."""
    return SqlStoredFileRepository(db)


def get_storage_port(
    db: Annotated[Session, Depends(get_db, scope="function")],
) -> StoragePort:
    """Dependency provider for StoragePort."""
    return make_storage(db)
