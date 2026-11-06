"""Auth module — application output DTOs."""
from __future__ import annotations

from pydantic import BaseModel


class TokenDTO(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
