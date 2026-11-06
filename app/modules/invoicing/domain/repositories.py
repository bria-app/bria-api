"""Invoicing module domain — repository port."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.invoicing.domain.entities import Invoice


class InvoiceRepository(Protocol):
    """Port for Invoice persistence."""

    def get_by_id(self, invoice_id: UUID) -> Invoice | None: ...
    def list_by_company(self, company_id: UUID) -> list[Invoice]: ...
    def next_correlativo(self, company_id: UUID, series: str) -> int: ...
    def add(self, invoice: Invoice) -> Invoice: ...
    def update(self, invoice: Invoice) -> Invoice: ...
