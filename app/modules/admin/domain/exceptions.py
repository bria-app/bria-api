"""Admin module domain — exceptions."""
from __future__ import annotations

from app.shared.domain.errors import NotFoundError


class SettingNotFoundError(NotFoundError):
    def __init__(self, key: str) -> None:
        super().__init__(
            message=f"No encontramos el ajuste «{key}». Revisa el nombre.",
            details={"key": key},
        )
