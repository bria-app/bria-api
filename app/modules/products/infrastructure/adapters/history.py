"""Products module — does anything in the shop's history point at a product?

Read-only existence checks across the tables that keep a ``product_id`` (sales, POS
lines, purchases, the inventory ledger, lost sales, forecasts, recommendations, KPIs).
Used to refuse a hard delete that would orphan those rows.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.forecasting.infrastructure.persistence.models import (
    ForecastMetricsModel,
    ForecastResultModel,
)
from app.modules.inventory.infrastructure.persistence.models import (
    InventoryMovementModel,
    ReplenishmentModel,
    StockoutEventModel,
    StockSnapshotModel,
)
from app.modules.kpis.infrastructure.persistence.models import KpiModel
from app.modules.purchases.infrastructure.persistence.models import PurchaseModel
from app.modules.recommendations.infrastructure.persistence.models import RecommendationModel
from app.modules.sales.infrastructure.persistence.models import LostSaleModel, SaleModel

# Tables scoped by company as well as by product.
_COMPANY_TABLES = (
    SaleModel,
    PurchaseModel,
    InventoryMovementModel,
    LostSaleModel,
    RecommendationModel,
    ForecastResultModel,
    KpiModel,
    StockSnapshotModel,
    ReplenishmentModel,
    StockoutEventModel,
)
# Tables keyed by run only (product ids are UUIDs, unique across companies).
_PRODUCT_TABLES = (ForecastMetricsModel,)


class SqlProductHistory:
    def __init__(self, session: Session) -> None:
        self._session = session

    def has_history(self, company_id: UUID, product_id: UUID) -> bool:
        for model in _COMPANY_TABLES:
            stmt = (
                select(model.id)
                .where(model.company_id == company_id, model.product_id == product_id)
                .limit(1)
            )
            if self._session.execute(stmt).first() is not None:
                return True
        for model in _PRODUCT_TABLES:
            stmt = select(model.id).where(model.product_id == product_id).limit(1)
            if self._session.execute(stmt).first() is not None:
                return True
        return False
