"""Bloque 2 — focused unit tests for the critical new logic.

Covers: inventory stock derivation, product SKU uniqueness, and the forecasting run
execution (success + failure) with in-memory fakes and a fake FTGM engine.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.modules.data_preparation.domain.entities import (
    PreparedDataset,
    PreparedTimeSeries,
)
from app.modules.forecasting.application.ports import ProductForecast
from app.modules.forecasting.application.use_cases.execution import ExecuteForecastRun
from app.modules.forecasting.domain.entities import (
    ForecastMetrics,
    ForecastResult,
    ForecastRun,
)
from app.modules.forecasting.domain.value_objects import ForecastPoint
from app.modules.inventory.domain.entities import InventoryMovement
from app.modules.inventory.domain.enums import MovementType
from app.modules.inventory.domain.services import compute_stock_on_hand
from app.modules.products.application.use_cases.product import CreateProduct
from app.modules.products.domain.entities import Product
from app.modules.products.domain.exceptions import ProductAlreadyExistsError
from app.shared.domain.value_objects import Quantity


# --- Inventory: derived stock ------------------------------------------------
def _movement(mt: MovementType, qty: int) -> InventoryMovement:
    return InventoryMovement(
        company_id=uuid4(),
        product_id=uuid4(),
        movement_type=mt,
        quantity=Quantity(qty),
        reason="",
        occurred_at=datetime.now(timezone.utc),
    )


def test_compute_stock_on_hand() -> None:
    movements = [
        _movement(MovementType.INBOUND, 100),
        _movement(MovementType.OUTBOUND, 30),
        _movement(MovementType.ADJUSTMENT, 5),
        _movement(MovementType.OUTBOUND, 10),
    ]
    assert compute_stock_on_hand(movements) == 65


# --- Products: SKU uniqueness ------------------------------------------------
class FakeProductRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Product] = {}

    def get_by_id(self, product_id: UUID) -> Product | None:
        return self._store.get(product_id)

    def get_by_sku(self, company_id: UUID, sku: str) -> Product | None:
        return next(
            (
                p
                for p in self._store.values()
                if p.company_id == company_id and p.sku.value == sku
            ),
            None,
        )

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Product]:
        return [p for p in self._store.values() if p.company_id == company_id]

    def list_active(self, company_id: UUID) -> list[Product]:
        return [p for p in self._store.values() if p.is_active]

    def add(self, product: Product) -> Product:
        if product.id is None:
            product.id = uuid4()
        self._store[product.id] = product
        return product

    def update(self, product: Product) -> Product:
        assert product.id is not None
        self._store[product.id] = product
        return product

    def delete(self, product_id: UUID) -> bool:
        return self._store.pop(product_id, None) is not None


def test_create_product_duplicate_sku_raises() -> None:
    repo = FakeProductRepository()
    company_id = uuid4()
    CreateProduct(repo).execute(
        company_id, sku="ABC-1", name="Dog food", unit_cost=Decimal("10"), unit_price=Decimal("15")
    )
    with pytest.raises(ProductAlreadyExistsError):
        CreateProduct(repo).execute(
            company_id, sku="abc-1", name="Dup", unit_cost=Decimal("9"), unit_price=Decimal("12")
        )


# --- Forecasting: run execution ---------------------------------------------
class FakeRunRepository:
    def __init__(self, run: ForecastRun) -> None:
        self.run = run

    def get_by_id(self, run_id: UUID) -> ForecastRun | None:
        return self.run if self.run.id == run_id else None

    def get_latest_by_company(self, company_id: UUID) -> ForecastRun | None:
        return self.run

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[ForecastRun]:
        return [self.run]

    def add(self, run: ForecastRun) -> ForecastRun:
        self.run = run
        return run

    def update(self, run: ForecastRun) -> ForecastRun:
        self.run = run
        return run


class FakeResultRepository:
    def __init__(self) -> None:
        self.items: list[ForecastResult] = []

    def get_by_run_and_product(
        self, run_id: UUID, product_id: UUID
    ) -> ForecastResult | None:
        return None

    def list_by_run(self, run_id: UUID) -> list[ForecastResult]:
        return self.items

    def add(self, result: ForecastResult) -> ForecastResult:
        self.items.append(result)
        return result

    def add_bulk(self, results: list[ForecastResult]) -> list[ForecastResult]:
        self.items.extend(results)
        return results


class FakeMetricsRepository:
    def __init__(self) -> None:
        self.items: list[ForecastMetrics] = []

    def get_by_run_and_product(
        self, run_id: UUID, product_id: UUID
    ) -> ForecastMetrics | None:
        return None

    def list_by_run(self, run_id: UUID) -> list[ForecastMetrics]:
        return self.items

    def add(self, metrics: ForecastMetrics) -> ForecastMetrics:
        self.items.append(metrics)
        return metrics

    def add_bulk(self, metrics: list[ForecastMetrics]) -> list[ForecastMetrics]:
        self.items.extend(metrics)
        return metrics


class FakeDatasetRepository:
    def __init__(self, dataset: PreparedDataset) -> None:
        self.dataset = dataset

    def get_by_id(self, dataset_id: UUID) -> PreparedDataset | None:
        return self.dataset

    def list_by_company(self, company_id: UUID) -> list[PreparedDataset]:
        return [self.dataset]

    def add(self, dataset: PreparedDataset) -> PreparedDataset:
        return dataset

    def update(self, dataset: PreparedDataset) -> PreparedDataset:
        return dataset

    def delete(self, dataset_id: UUID) -> bool:
        return True


class FakeEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def forecast(
        self,
        *,
        series: list[PreparedTimeSeries],
        horizon_days: int,
        model_name: str,
        **_: object,  # frequency / as_of added by the scoped-run contract
    ) -> list[ProductForecast]:
        if self._fail:
            raise RuntimeError("engine unreachable")
        return [
            ProductForecast(
                product_id=s.product_id,
                points=[
                    ForecastPoint(
                        period_date=date(2026, 7, 1),
                        predicted_demand=Decimal("12.5"),
                    )
                ],
                mape=Decimal("8.5"),
                mae=Decimal("1.2"),
                rmse=Decimal("1.8"),
            )
            for s in series
        ]


def _setup(*, fail: bool) -> tuple[ExecuteForecastRun, UUID, FakeRunRepository]:
    company_id = uuid4()
    dataset_id = uuid4()
    run = ForecastRun(
        id=uuid4(),
        company_id=company_id,
        model_name="FTGM",
        horizon_days=30,
        dataset_id=dataset_id,
    )
    dataset = PreparedDataset(
        id=dataset_id,
        company_id=company_id,
        series=[PreparedTimeSeries(dataset_id=dataset_id, product_id=uuid4())],
    )
    runs = FakeRunRepository(run)
    uc = ExecuteForecastRun(
        runs=runs,
        results=FakeResultRepository(),
        metrics=FakeMetricsRepository(),
        datasets=FakeDatasetRepository(dataset),
        engine=FakeEngine(fail=fail),
    )
    assert run.id is not None
    return uc, run.id, runs


def test_execute_forecast_run_success() -> None:
    uc, run_id, runs = _setup(fail=False)
    result = uc.execute(run_id)
    assert result.status == "success"
    assert runs.run.completed_at is not None


def test_execute_forecast_run_failure_marks_failed() -> None:
    uc, run_id, runs = _setup(fail=True)
    result = uc.execute(run_id)
    assert result.status == "failed"
    assert result.error_message == "engine unreachable"
