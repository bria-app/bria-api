"""KPIs module — cross-module orchestration to compute KPIs for a company.

Combines the three inputs of the DSS:
1. the forecast (latest successful ForecastRun + its per-product results),
2. the current stock (derived from the inventory movement ledger),
3. the product parameters (lead time, safety stock).
Applies the pure KPI formulas and persists one Kpi per (product, KpiType).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.modules.forecasting.application.latest import (
    latest_results_by_product,
    to_daily_demand,
)
from app.modules.forecasting.domain.repositories import (
    ForecastResultRepository,
    ForecastRunRepository,
)
from app.modules.inventory.domain.repositories import InventoryMovementRepository
from app.modules.inventory.domain.services import compute_stock_on_hand
from app.modules.kpis.application.dtos import KpiDTO
from app.modules.kpis.domain.entities import Kpi
from app.modules.kpis.domain.repositories import KpiRepository
from app.modules.kpis.domain.services import ProductKpiInputs, compute_all
from app.modules.products.domain.repositories import ProductRepository
from app.shared.domain.errors import ValidationError

_MOVE_PAGE = 200


class ComputeCompanyKpis:
    def __init__(
        self,
        *,
        products: ProductRepository,
        runs: ForecastRunRepository,
        results: ForecastResultRepository,
        movements: InventoryMovementRepository,
        kpis: KpiRepository,
    ) -> None:
        self._products = products
        self._runs = runs
        self._results = results
        self._movements = movements
        self._kpis = kpis

    def _current_stock(self, product_id: UUID) -> int:
        collected = []
        offset = 0
        while True:
            page = self._movements.list_by_product(product_id, offset, _MOVE_PAGE)
            collected.extend(page)
            if len(page) < _MOVE_PAGE:
                break
            offset += _MOVE_PAGE
        return compute_stock_on_hand(collected)

    def execute(self, company_id: UUID) -> list[KpiDTO]:
        # Each product uses the freshest successful run that forecast it (runs may cover
        # one product, a supplier, a category…), with its own period length.
        latest = latest_results_by_product(self._runs, self._results, company_id)
        if not latest:
            raise ValidationError(
                message="Primero calcula un pronóstico en Pronóstico."
            )
        computed_at = datetime.now(timezone.utc)

        to_add: list[Kpi] = []
        for product in self._products.list_active(company_id):
            if product.id is None or product.id not in latest:
                continue
            run, result = latest[product.id]
            run_id = run.id
            inputs = ProductKpiInputs(
                current_stock=self._current_stock(product.id),
                daily_demand=to_daily_demand(result.points, run.frequency),
                lead_time_days=product.lead_time_days,
                safety_stock=product.safety_stock,
            )
            for kpi_type, value in compute_all(inputs).items():
                to_add.append(
                    Kpi(
                        company_id=company_id,
                        product_id=product.id,
                        kpi_type=kpi_type,
                        value=value,
                        computed_at=computed_at,
                        run_id=run_id,
                    )
                )

        return [KpiDTO.from_entity(k) for k in self._kpis.add_bulk(to_add)]
