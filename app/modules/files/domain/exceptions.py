"""Files module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import NotFoundError


class StoredFileNotFoundError(NotFoundError):
    def __init__(self, file_id: UUID) -> None:
        super().__init__(
            message="No encontramos ese archivo. Actualiza la página e inténtalo de nuevo.",
            details={"file_id": str(file_id)},
        )
