"""Shared application ports — interfaces the use cases depend on; adapters live in infrastructure."""
from __future__ import annotations

from typing import Protocol


class StoragePort(Protocol):
    """Stores and retrieves files (datasets, images, reports)."""

    def save(self, file_name: str, content: bytes, content_type: str) -> str:
        """Saves a file and returns its URI or path."""
        ...

    def get(self, file_path: str) -> bytes:
        """Retrieves a file's content by its URI or path."""
        ...

    def delete(self, file_path: str) -> bool:
        """Deletes a file by its URI or path."""
        ...
