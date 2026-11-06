"""Suppliers module domain — repository ports."""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.modules.suppliers.domain.entities import Supplier


class SupplierRepository(Protocol):
    """Port for Supplier persistence."""

    def get_by_id(self, supplier_id: UUID) -> Supplier | None: ...
    def get_by_ruc(self, company_id: UUID, ruc: str) -> Supplier | None: ...
    def list_by_company(self, company_id: UUID) -> list[Supplier]: ...
    def add(self, supplier: Supplier) -> Supplier: ...
    def update(self, supplier: Supplier) -> Supplier: ...
    def delete(self, supplier_id: UUID) -> bool: ...


class SupplierStatsReader(Protocol):
    """Read-side port: purchase figures per supplier (fed by the purchases table)."""

    def totals_by_supplier(self, company_id: UUID) -> dict[UUID, dict[str, Any]]: ...
    def summary(self, company_id: UUID, supplier_id: UUID) -> dict[str, Any]: ...


class UnitOfWorkSavepoint(Protocol):
    """Runs a block inside a savepoint so one bad import row doesn't sink the rest."""

    def savepoint(self) -> Any: ...
