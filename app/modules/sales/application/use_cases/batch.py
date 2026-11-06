"""Sales module — use cases for the SalesBatch aggregate."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from app.modules.sales.application.dtos import SalesBatchDTO
from app.modules.sales.domain.entities import SalesBatch
from app.modules.sales.domain.exceptions import SalesBatchNotFoundError
from app.modules.sales.domain.repositories import SalesBatchRepository
from app.shared.domain.value_objects import DateRange


class CreateSalesBatch:
    def __init__(self, batches: SalesBatchRepository) -> None:
        self._batches = batches

    def execute(
        self,
        company_id: UUID,
        *,
        source_file: str,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> SalesBatchDTO:
        period = None
        if period_start is not None and period_end is not None:
            period = DateRange(period_start, period_end)
        batch = SalesBatch(
            company_id=company_id, source_file=source_file, period=period
        )
        return SalesBatchDTO.from_entity(self._batches.add(batch))


class GetSalesBatch:
    def __init__(self, batches: SalesBatchRepository) -> None:
        self._batches = batches

    def execute(self, company_id: UUID, batch_id: UUID) -> SalesBatchDTO:
        batch = self._batches.get_by_id(batch_id)
        if batch is None or batch.company_id != company_id:
            raise SalesBatchNotFoundError(message="No encontramos esa carga de ventas. Actualiza la página e inténtalo de nuevo.")
        return SalesBatchDTO.from_entity(batch)


class ListSalesBatches:
    def __init__(self, batches: SalesBatchRepository) -> None:
        self._batches = batches

    def execute(self, company_id: UUID) -> list[SalesBatchDTO]:
        return [
            SalesBatchDTO.from_entity(b)
            for b in self._batches.list_by_company(company_id)
        ]
