"""Local filesystem implementation of StoragePort (development storage)."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.config import settings


class LocalFileStorage:
    """Stores files under ``settings.storage_root``. Implements StoragePort."""

    def __init__(self, root: str | None = None) -> None:
        self._root = Path(root or settings.storage_root)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, file_name: str, content: bytes, content_type: str) -> str:
        safe_name = f"{uuid4().hex}_{Path(file_name).name}"
        path = self._root / safe_name
        path.write_bytes(content)
        return str(path)

    def get(self, file_path: str) -> bytes:
        return Path(file_path).read_bytes()

    def delete(self, file_path: str) -> bool:
        path = Path(file_path)
        if not path.exists():
            return False
        path.unlink()
        return True
