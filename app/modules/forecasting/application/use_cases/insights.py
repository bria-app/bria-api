"""Forecasting — read models over finished runs: tracking, per-product history, overview."""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Any
from uuid import UUID

from app.modules.forecasting.application.dtos import (
    ForecastMetricsDTO,
    ForecastRunDTO,
    run_engine_mode,
)
from app.modules.forecasting.domain.entities import ForecastResult, ForecastRun
from app.modules.forecasting.application.latest import to_daily_demand
from app.modules.forecasting.application.use_cases.run import owned_run
from app.modules.forecasting.application.ports import ErpHistorySource
from app.modules.forecasting.domain.repositories import (
    ForecastMetricsRepository,
    ForecastResultRepository,
    ForecastRunRepository,
)
from app.modules.forecasting.domain.tracking import infer_frequency, track_product
from app.modules.recommendations.domain.repositories import RecommendationRepository
from app.modules.recommendations.domain.services import SAFETY_MARGIN_DAYS, effective_lead_time
from app.modules.sales.domain.services import lima_today



def _days_covered(on_hand: int, by_day: list[float]) -> float:
    """Days until the forecast demand, day by day, uses up what is on the shelf."""
    if on_hand <= 0:
        return 0.0
    left = float(on_hand)
    for day, units in enumerate(by_day):
        if units >= left:
            return day + left / units
        left -= units
    # Lasts beyond the horizon: extrapolate at the horizon's average rate.
    rate = sum(by_day) / len(by_day) if by_day else 0.0
    return len(by_day) + left / rate if rate > 0 else float(len(by_day))


def _get_run(runs: ForecastRunRepository, company_id: UUID, run_id: UUID) -> ForecastRun:
    return owned_run(runs, company_id, run_id)


def _product_frequency(run: ForecastRun, result: ForecastResult) -> str:
    diag = (run.meta.get("diagnostics") or {}).get(str(result.product_id)) or {}
    return infer_frequency(result.points, diag.get("frequency") or run.frequency)


class TrackForecastRun:
    """``GET /forecast-runs/{id}/tracking`` — forecast vs what actually sold."""

    def __init__(self, runs: ForecastRunRepository, results: ForecastResultRepository, source: ErpHistorySource) -> None:
        self._runs = runs
        self._results = results
        self._source = source

    def for_run(self, run: ForecastRun, product_id: UUID | None = None) -> dict[str, Any]:
        assert run.id is not None
        results = [
            r for r in self._results.list_by_run(run.id) if r.points and (product_id is None or r.product_id == product_id)
        ]
        today = lima_today()
        products = self._source.products_by_ids(run.company_id, [r.product_id for r in results])
        start = min((r.points[0].period_date for r in results), default=today)
        sales = self._source.sales_by_day(
            run.company_id, [r.product_id for r in results], start, today + timedelta(days=1)
        )
        items = []
        for r in results:
            freq = _product_frequency(run, r)
            tracked = track_product(r.points, freq, sales.get(r.product_id, {}), today)
            p = products.get(r.product_id)
            tracked.update(product_id=str(r.product_id), sku=p.sku if p else "", name=p.name if p else "")
            items.append(tracked)
        elapsed = [i for i in items if i["periods_elapsed"] > 0]
        fc = sum(i["forecast_to_date"] for i in elapsed)
        act = sum(i["actual_to_date"] for i in elapsed)
        return {
            "run_id": str(run.id),
            "today": today.isoformat(),
            "as_of": run.meta.get("as_of"),
            "forecast_to_date": round(fc, 2),
            "actual_to_date": round(act, 2),
            "bias_pct": round((fc - act) / act * 100, 2) if act > 0 else None,
            "products_on_track": sum(1 for i in items if i["status"] == "en_linea"),
            "products_over": sum(1 for i in items if i["status"] == "sobre_pronostico"),
            "products_under": sum(1 for i in items if i["status"] == "bajo_pronostico"),
            "products_pending": sum(1 for i in items if i["status"] == "pendiente"),
            "products": items,
        }

    def execute(self, company_id: UUID, run_id: UUID) -> dict[str, Any]:
        return self.for_run(_get_run(self._runs, company_id, run_id))


class ListProductRuns:
    """``GET /forecast-runs/by-product/{product_id}`` — past runs with tracking summary."""

    def __init__(self, runs: ForecastRunRepository, tracking: TrackForecastRun, source: ErpHistorySource) -> None:
        self._runs = runs
        self._tracking = tracking
        self._source = source

    def execute(self, company_id: UUID, product_id: UUID, limit: int = 10) -> list[dict[str, Any]]:
        out = []
        for run_id in self._source.run_ids_for_product(company_id, product_id, limit):
            run = self._runs.get_by_id(run_id)
            if run is None or run.company_id != company_id or run.is_backtest:
                continue
            tracked = self._tracking.for_run(run, product_id) if run.status.value == "success" else None
            product_tracking = tracked["products"][0] if tracked and tracked["products"] else None
            diag = (run.meta.get("diagnostics") or {}).get(str(product_id))
            out.append(
                {
                    "run": ForecastRunDTO.from_entity(run).model_dump(mode="json"),
                    "tracking": product_tracking,
                    "diagnostics": diag,
                }
            )
        return out


class GetRunOverview:
    """``GET /forecast-runs/{id}/overview`` — executive summary + per-product decision rows."""

    def __init__(
        self,
        runs: ForecastRunRepository,
        results: ForecastResultRepository,
        metrics: ForecastMetricsRepository,
        recommendations: RecommendationRepository,
        source: ErpHistorySource,
    ) -> None:
        self._runs = runs
        self._results = results
        self._metrics = metrics
        self._recs = recommendations
        self._source = source

    def execute(self, company_id: UUID, run_id: UUID) -> dict[str, Any]:
        run = _get_run(self._runs, company_id, run_id)
        results = {r.product_id: r for r in self._results.list_by_run(run_id)}
        metrics = {m.product_id: m for m in self._metrics.list_by_run(run_id)}
        products = self._source.products_by_ids(company_id, list(results) or [UUID(p) for p in run.product_ids or []])
        stock = self._source.stock_map(company_id)
        pending = {r.product_id: r for r in self._recs.list_pending(company_id)}
        diagnostics = run.meta.get("diagnostics") or {}

        rows: list[dict[str, Any]] = []
        for pid, result in results.items():
            p = products.get(pid)
            m = metrics.get(pid)
            diag = diagnostics.get(str(pid)) or {}
            freq = _product_frequency(run, result) if result.points else (diag.get("frequency") or "monthly")
            points = result.points
            next_units = float(points[0].predicted_demand) if points else 0.0
            total_units = sum(float(x.predicted_demand) for x in points)
            on_hand = stock.get(pid, 0)
            lead = effective_lead_time(p.lead_time_days if p else 0)
            safety = p.safety_stock if p else 0
            reorder = p.reorder_point if p else 0
            # The same day-by-day demand the recommendations use: one quiet first week must
            # not read as "stock for 2,100 days", nor one busy week as an emergency.
            by_day = [float(v) for v in to_daily_demand(points, freq)] if points else []
            window = by_day[: lead + SAFETY_MARGIN_DAYS] or by_day
            daily = sum(window) / len(window) if window else 0.0
            coverage = _days_covered(on_hand, by_day) if daily > 0 else None
            if daily <= 0:
                risk = "bajo"
            elif on_hand <= 0 or (coverage is not None and coverage < max(lead, 3)):
                risk = "alto"
            elif on_hand < daily * (lead + SAFETY_MARGIN_DAYS) + safety:
                risk = "medio"
            else:
                risk = "bajo"
            rec = pending.get(pid)
            # Same rule everywhere: stock below the supplier's wait + two weeks + safety stock.
            short = on_hand < daily * (lead + SAFETY_MARGIN_DAYS) + safety
            needs = bool(rec) or (daily > 0 and (on_hand <= reorder or short))
            if rec:
                qty = int(rec.recommended_quantity.value)
            elif needs:
                qty = max(0, math.ceil(daily * (lead + 30) + safety - on_hand))
            else:
                qty = 0
            unit_cost = float(p.unit_cost) if p else 0.0
            rows.append(
                {
                    "product_id": str(pid),
                    "sku": p.sku if p else "",
                    "name": p.name if p else "",
                    "unit_cost": unit_cost,
                    "on_hand": on_hand,
                    "lead_time_days": lead,
                    "safety_stock": safety,
                    "frequency": freq,
                    "status": m.status if m else "ok",
                    "model_used": m.model_used if m else "",
                    "order_selected": m.order_selected if m else 0,
                    "fallback_reason": m.fallback_reason if m else None,
                    "metrics": ForecastMetricsDTO.from_entity(m).model_dump(mode="json") if m else None,
                    "holdout": diag.get("holdout"),
                    "skill_vs_naive": diag.get("skill_vs_naive"),
                    "accuracy_pct": diag.get("accuracy_pct"),
                    "trend_pct": diag.get("forecast_vs_recent_pct"),
                    "next_period": points[0].period_date.isoformat() if points else None,
                    "next_period_units": round(next_units, 2),
                    "total_forecast_units": round(total_units, 2),
                    "coverage_days": round(coverage, 1) if coverage is not None else None,
                    "stockout_risk": risk,
                    "needs_restock": needs and qty > 0,
                    "suggested_qty": qty,
                    "suggested_investment": round(qty * unit_cost, 2),
                    "recommendation_id": str(rec.id) if rec and rec.id else None,
                }
            )
        rows.sort(key=lambda r: ({"alto": 0, "medio": 1, "bajo": 2}[r["stockout_risk"]], -r["total_forecast_units"]))
        summary = {
            "total_forecast_units": round(sum(r["total_forecast_units"] for r in rows), 1),
            "next_period_units": round(sum(r["next_period_units"] for r in rows), 1),
            "products": len(rows),
            "products_need_restock": sum(1 for r in rows if r["needs_restock"]),
            "risk_high": sum(1 for r in rows if r["stockout_risk"] == "alto"),
            "risk_medium": sum(1 for r in rows if r["stockout_risk"] == "medio"),
            "suggested_investment": round(sum(r["suggested_investment"] for r in rows), 2),
            "products_ok": sum(1 for r in rows if r["status"] == "ok"),
            "products_fallback": sum(1 for r in rows if r["status"] == "fallback"),
            "products_skipped": sum(1 for r in rows if r["status"] == "skipped"),
            # Plain accuracy of the whole run, weighted by how much each product sells.
            "accuracy_pct": _weighted_accuracy(rows),
            # "mock" = demo engine (simulated numbers): the web shows the demo banner.
            "ftgm_engine_mode": run_engine_mode(run),
        }
        return {
            "run": ForecastRunDTO.from_entity(run).model_dump(mode="json"),
            "summary": summary,
            "preview": run.meta.get("preview"),
            "products": rows,
            "diagnostics": diagnostics,
        }


def _weighted_accuracy(rows: list[dict[str, Any]]) -> float | None:
    pairs = [
        (float(r["accuracy_pct"]), float(r["total_forecast_units"]))
        for r in rows
        if r.get("accuracy_pct") is not None and r["total_forecast_units"] > 0
    ]
    weight = sum(w for _, w in pairs)
    return round(sum(a * w for a, w in pairs) / weight, 1) if weight > 0 else None
