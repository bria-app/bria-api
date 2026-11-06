"""Forecasting — ERP-scoped runs: preview, plan gating, creation and product insight.

A *scope* picks products straight from the ERP (recent sales, supplier, seller,
category, specific products, whole catalog). The demand history is built from the sales
table (plus lost sales / movements for stock-outs) — no CSV, no manual preparation.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable
from uuid import UUID, uuid4

from app.modules.data_preparation.domain import erp_analysis as ea
from app.modules.data_preparation.domain.entities import PreparedDataset, PreparedTimeSeries
from app.modules.data_preparation.domain.enums import DatasetStatus
from app.modules.data_preparation.domain.repositories import PreparedDatasetRepository
from app.modules.forecasting.application.dtos import ForecastRunDTO
from app.modules.forecasting.application.ports import ErpHistorySource
from app.modules.forecasting.domain.entities import ForecastRun
from app.modules.forecasting.domain.repositories import ForecastRunRepository
from app.modules.sales.domain.services import lima_today
from app.shared.domain.errors import ForbiddenError, NotFoundError, ValidationError
from app.shared.domain.value_objects import DateRange

FREE_PLAN_MESSAGE = (
    "Ya usaste tus {limit} predicciones gratis de este mes. "
    "Con Premium predices sin límites, o espera al próximo mes."
)
FREQUENCIES = ("auto", "monthly", "weekly")


def enforce_plan(is_premium: bool, runs_used: int, monthly_limit: int) -> None:
    """Free plan: any scope (whole catalog included), but only a few runs per month."""
    if is_premium:
        return
    if runs_used >= monthly_limit:
        raise ForbiddenError(
            message=FREE_PLAN_MESSAGE.format(limit=monthly_limit),
            details={"plan": "free", "monthly_limit": monthly_limit, "used": runs_used},
        )


def _resolve_as_of(as_of: date | None) -> date:
    today = lima_today()
    if as_of is None:
        return today
    if as_of > today:
        raise ValidationError(message="La fecha de corte no puede estar en el futuro.")
    return as_of


class PreviewForecastScope:
    """``POST /forecast-runs/scope-preview`` — what would go to the FTGM engine."""

    def __init__(self, source: ErpHistorySource, is_premium: Callable[[UUID], bool]) -> None:
        self._source = source
        self._is_premium = is_premium

    def build(
        self, company_id: UUID, scope: dict[str, Any], frequency: str = "auto", as_of: date | None = None
    ) -> tuple[dict[str, Any], list[ea.ProductHistory]]:
        if frequency not in FREQUENCIES:
            raise ValidationError(message="Frecuencia inválida (auto, monthly o weekly).")
        cutoff = _resolve_as_of(as_of)
        products = self._source.resolve_scope(company_id, scope, cutoff)
        histories = self._source.load_histories(company_id, products, cutoff)
        latest = self._source.latest_runs(company_id, [p.id for p in products])
        rows = []
        for h in histories:
            row = ea.analyze(h, cutoff, frequency)
            prev = latest.get(h.product_id)
            row["latest_run_id"] = prev["run_id"] if prev else None
            row["latest_run_at"] = prev["created_at"] if prev else None
            rows.append(row)
        # Ready first, then low data, then excluded; bigger sellers first inside each group.
        order = {ea.READY: 0, ea.LOW_DATA: 1, ea.NO_SALES: 2}
        rows.sort(key=lambda r: (order.get(r["readiness"], 3), -r["total_units"]))
        totals = ea.consolidate(rows, frequency, cutoff)
        totals["description"] = self._source.describe(company_id, scope, len(rows))
        return {"scope": scope, "totals": totals, "products": rows}, histories

    def execute(
        self, company_id: UUID, scope: dict[str, Any], frequency: str = "auto", as_of: date | None = None
    ) -> dict[str, Any]:
        # Previewing is free on every plan; the quota only counts launched runs.
        preview, _ = self.build(company_id, scope, frequency, as_of)
        return preview


class CreateScopedForecastRun:
    """Build the dataset from the ERP, persist the run with its scope (job started by caller)."""

    def __init__(
        self,
        runs: ForecastRunRepository,
        datasets: PreparedDatasetRepository,
        preview: PreviewForecastScope,
        is_premium: Callable[[UUID], bool],
        runs_used: Callable[[UUID], int],
        monthly_limit: int,
    ) -> None:
        self._runs = runs
        self._datasets = datasets
        self._preview = preview
        self._is_premium = is_premium
        self._runs_used = runs_used
        self._monthly_limit = monthly_limit

    def execute(
        self,
        company_id: UUID,
        *,
        scope: dict[str, Any],
        horizon_days: int,
        frequency: str = "auto",
        model_name: str = "FTGM",
        as_of: date | None = None,
    ) -> ForecastRunDTO:
        enforce_plan(self._is_premium(company_id), self._runs_used(company_id), self._monthly_limit)
        cutoff = _resolve_as_of(as_of)
        preview, histories = self._preview.build(company_id, scope, frequency, cutoff)
        included_ids = {r["product_id"] for r in preview["products"] if r["included"]}
        if not included_ids:
            raise ValidationError(
                message="Ningún producto del alcance tiene ventas en periodos completos para pronosticar."
            )

        dataset_id = uuid4()
        series = []
        for h in histories:
            if str(h.product_id) not in included_ids:
                continue
            points = ea.build_points(h, cutoff)
            if not points:
                continue
            series.append(
                PreparedTimeSeries(
                    dataset_id=dataset_id,
                    product_id=h.product_id,
                    points=points,
                    has_stockout_flags=any(p.is_stockout for p in points),
                    outliers_treated=False,
                )
            )
        if not series:
            raise ValidationError(message="No hay observaciones de venta para enviar al motor FTGM.")
        all_dates = [p.period_date for s in series for p in s.points]
        self._datasets.add(
            PreparedDataset(
                id=dataset_id,
                company_id=company_id,
                source_batch_id=None,
                status=DatasetStatus.READY,
                product_count=len(series),
                period=DateRange(min(all_dates), max(all_dates)),
                series=series,
            )
        )

        totals = preview["totals"]
        stored_scope = dict(scope)
        stored_scope["_meta"] = {
            "as_of": cutoff.isoformat(),
            "backtest": cutoff < lima_today(),
            "description": totals["description"],
            "product_count": len(series),
            "preview": {
                k: totals[k]
                for k in (
                    "frequency",
                    "products_included",
                    "products_excluded",
                    "products_ready",
                    "products_low_data",
                    "total_data_points",
                    "date_start",
                    "date_end",
                    "excluded",
                )
            },
        }
        run = ForecastRun(
            company_id=company_id,
            model_name=model_name,
            horizon_days=horizon_days,
            dataset_id=dataset_id,
            scope=stored_scope,
            product_ids=[str(s.product_id) for s in series],
            frequency=frequency,
        )
        return ForecastRunDTO.from_entity(self._runs.add(run))


class GetProductInsight:
    """Stock level, sales, restocks and stock-outs per period for one product (charts)."""

    def __init__(self, source: ErpHistorySource) -> None:
        self._source = source

    def execute(self, company_id: UUID, product_id: UUID, frequency: str = "weekly", periods: int = 52) -> dict[str, Any]:
        if frequency not in ("weekly", "monthly"):
            raise ValidationError(message="Frecuencia inválida (weekly o monthly).")
        products = self._source.products_by_ids(company_id, [product_id])
        product = products.get(product_id)
        if product is None:
            raise NotFoundError(message="No encontramos ese producto. Actualiza la página e inténtalo de nuevo.")
        today = lima_today()
        (h,) = self._source.load_histories(company_id, [product], today + timedelta(days=1))
        info = ea.detect_stockouts(h, today + timedelta(days=1))

        end = ea.next_bucket(ea.bucket_start(today, frequency), frequency)
        start = ea.bucket_start(today, frequency)
        for _ in range(max(1, periods) - 1):
            start = ea.bucket_start(start - timedelta(days=1), frequency)
        buckets = ea.iter_buckets(start, end, frequency)
        stock = ea.stock_levels(h, info, buckets, frequency)

        rows = []
        for b in buckets:
            nb = ea.next_bucket(b, frequency)
            rows.append(
                {
                    "period": b.isoformat(),
                    "partial": nb > today + timedelta(days=1),
                    "units": sum(u for d, u in h.sales.items() if b <= d < nb),
                    "lost_units": sum(u for d, (_, u) in h.lost.items() if b <= d < nb),
                    "stockout_days": sum(1 for d in info.days if b <= d < nb),
                    "restock_units": sum(q for d, q in h.purchases if b <= d < nb),
                    "stock_end": stock.get(b),
                }
            )
        analysis = ea.analyze(h, today, "auto")
        return {
            "product_id": str(product_id),
            "sku": product.sku,
            "name": product.name,
            "frequency": frequency,
            "on_hand": h.on_hand,
            "safety_stock": product.safety_stock,
            "reorder_point": product.reorder_point,
            "ledger_reliable": info.ledger_consistent,
            "restocks": [
                {"date": d.isoformat(), "units": q} for d, q in h.purchases if d >= start
            ],
            "periods": rows,
            "analysis": analysis,
        }
