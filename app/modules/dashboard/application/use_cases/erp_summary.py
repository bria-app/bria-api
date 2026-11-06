"""Dashboard — ERP-first summary use case."""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class ErpSummaryReader(Protocol):
    def summary(self, company_id: UUID) -> dict[str, Any]: ...


class GetErpSummary:
    def __init__(self, reader: ErpSummaryReader) -> None:
        self._reader = reader

    def execute(self, company_id: UUID) -> dict[str, Any]:
        return self._reader.summary(company_id)
