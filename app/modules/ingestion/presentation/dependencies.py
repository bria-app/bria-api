"""Ingestion module — presentation DI providers."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.ingestion.infrastructure.persistence.repositories import (
    SqlIngestionBatchRepository,
)
from app.shared.infrastructure.database import get_db
from app.shared.application.ports import StoragePort
from app.shared.infrastructure.storage.factory import make_storage


def get_ingestion_repository(
    db: Session = Depends(get_db, scope="function"),
) -> SqlIngestionBatchRepository:
    return SqlIngestionBatchRepository(db)


def get_storage(db: Session = Depends(get_db, scope="function")) -> StoragePort:
    return make_storage(db)
