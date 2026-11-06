"""Ingestion module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.ingestion.domain.entities import IngestionBatch


class IngestionBatchRepository(Protocol):
    """Port for IngestionBatch persistence."""

    def get_by_id(self, batch_id: UUID) -> IngestionBatch | None: ...
    def list_by_company(self, company_id: UUID) -> list[IngestionBatch]: ...
    def add(self, batch: IngestionBatch) -> IngestionBatch: ...
    def update(self, batch: IngestionBatch) -> IngestionBatch: ...
