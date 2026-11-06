"""Data preparation module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.data_preparation.domain.entities import PreparedDataset


class PreparedDatasetRepository(Protocol):
    """Port for PreparedDataset persistence."""

    def get_by_id(self, dataset_id: UUID) -> PreparedDataset | None: ...
    def list_by_company(self, company_id: UUID) -> list[PreparedDataset]: ...
    def add(self, dataset: PreparedDataset) -> PreparedDataset: ...
    def update(self, dataset: PreparedDataset) -> PreparedDataset: ...
    def delete(self, dataset_id: UUID) -> bool: ...
