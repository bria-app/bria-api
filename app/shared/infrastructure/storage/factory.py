"""Storage backend factory.

Selects the StoragePort implementation from ``settings.storage_backend``:

- ``"db"``    (default) — DbFileStorage: bytes live in Postgres, survive restarts.
- ``"local"``           — LocalFileStorage: bytes on disk (fine for local dev only;
                          data is lost on ephemeral filesystems).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.shared.application.ports import StoragePort
from app.shared.infrastructure.storage.db import DbFileStorage
from app.shared.infrastructure.storage.local import LocalFileStorage


def make_storage(db: Session) -> StoragePort:
    if settings.storage_backend == "local":
        return LocalFileStorage(settings.storage_root)
    return DbFileStorage(db)
