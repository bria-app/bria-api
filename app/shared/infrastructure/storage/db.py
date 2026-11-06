"""Database-backed implementation of StoragePort.

Stores file content as rows in Postgres instead of on the local filesystem, so
files survive restarts and redeploys on platforms with ephemeral disks (Render,
Railway free tiers). URIs are of the form ``db://<uuid>``.
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.shared.infrastructure.storage.models import StoredBlobModel

_SCHEME = "db://"


class DbFileStorage:
    """Stores/reads file bytes in the ``stored_blobs`` table. Implements StoragePort.

    Writes are flushed within the caller's request transaction; the per-request
    session (``get_db``) commits on success, so blobs persist across requests.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def save(self, file_name: str, content: bytes, content_type: str) -> str:
        blob = StoredBlobModel(
            id=uuid4(),
            file_name=Path(file_name).name,
            content_type=content_type or "application/octet-stream",
            size_bytes=len(content),
            content=content,
        )
        self._db.add(blob)
        self._db.flush()
        return f"{_SCHEME}{blob.id}"

    def get(self, file_path: str) -> bytes:
        blob = self._db.get(StoredBlobModel, self._parse_id(file_path))
        if blob is None:
            raise FileNotFoundError(f"Stored blob not found: {file_path}")
        return blob.content

    def delete(self, file_path: str) -> bool:
        blob = self._db.get(StoredBlobModel, self._parse_id(file_path))
        if blob is None:
            return False
        self._db.delete(blob)
        self._db.flush()
        return True

    @staticmethod
    def _parse_id(file_path: str) -> UUID:
        raw = file_path[len(_SCHEME):] if file_path.startswith(_SCHEME) else file_path
        return UUID(raw)
