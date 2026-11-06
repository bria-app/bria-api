"""Recommendations module — generate replenishment recommendations for a company.

Cross-module orchestration: latest forecast + derived stock + product parameters ->
reorder policy -> persisted Recommendation. A product keeps at most one pending
recommendation, and it always follows the freshest forecast: it is updated when the new
quantity differs and superseded when the new forecast no longer asks for a purchase (a
stale "buy 141" must not outlive the forecast that produced it).
"""
from __future__ import annotations

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
from app.modules.recommendations.application.dtos import RecommendationDTO
from app.modules.recommendations.domain.entities import Recommendation
from app.modules.recommendations.domain.repositories import RecommendationRepository
from app.modules.recommendations.domain.services import (
    ReorderInputs,
    suggest_reorder,
)
from app.modules.products.domain.repositories import ProductRepository
from app.shared.domain.errors import ValidationError
from app.shared.domain.value_objects import Quantity

_MOVE_PAGE = 200


class GenerateRecommendations:
    def __init__(
        self,
        *,
        products: ProductRepository,
        runs: ForecastRunRepository,
        results: ForecastResultRepository,
        movements: InventoryMovementRepository,
        recommendations: RecommendationRepository,
    ) -> None:
        self._products = products
        self._runs = runs
        self._results = results
        self._movements = movements
        self._recommendations = recommendations

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

    def execute(self, company_id: UUID) -> list[RecommendationDTO]:
        # Freshest successful forecast per product (single-product and scoped runs).
        latest = latest_results_by_product(self._runs, self._results, company_id)
        if not latest:
            raise ValidationError(
                message="Primero calcula un pronóstico en Pronóstico."
            )
        pending = {r.product_id: r for r in self._recommendations.list_pending(company_id)}

        created: list[RecommendationDTO] = []
        for product in self._products.list_active(company_id):
            if product.id is None or product.id not in latest:
                continue
            run, result = latest[product.id]
            suggestion = suggest_reorder(
                ReorderInputs(
                    current_stock=self._current_stock(product.id),
                    daily_demand=to_daily_demand(result.points, run.frequency),
                    lead_time_days=product.lead_time_days,
                    safety_stock=product.safety_stock,
                    reorder_point=product.reorder_point,
                )
            )
            current = pending.get(product.id)
            if current is not None:
                if suggestion is None:
                    current.supersede()
                    self._recommendations.update(current)
                elif current.refresh(Quantity(suggestion.quantity), suggestion.priority, suggestion.reason):
                    self._recommendations.update(current)
                continue
            if suggestion is None:
                continue
            recommendation = Recommendation(
                company_id=company_id,
                product_id=product.id,
                recommended_quantity=Quantity(suggestion.quantity),
                priority=suggestion.priority,
                reason=suggestion.reason,
            )
            created.append(
                RecommendationDTO.from_entity(
                    self._recommendations.add(recommendation)
                )
            )
        return created
