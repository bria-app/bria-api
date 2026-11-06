"""Ingestion module — presentation request schemas."""
from __future__ import annotations

from pydantic import BaseModel


class ColumnMappingRequest(BaseModel):
    mapping: dict[str, str]
