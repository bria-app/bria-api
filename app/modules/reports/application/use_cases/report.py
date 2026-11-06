"""Reports module — application use cases."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.modules.forecasting.domain.enums import RunStatus
from app.modules.forecasting.domain.repositories import (
    ForecastMetricsRepository,
    ForecastRunRepository,
)
from app.modules.kpis.domain.repositories import KpiRepository
from app.modules.products.domain.repositories import ProductRepository
from app.modules.recommendations.domain.repositories import RecommendationRepository
from app.modules.reports.application.dtos import ReportDTO
from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.enums import ReportType
from app.modules.reports.domain.exceptions import ReportNotFoundError
from app.modules.reports.domain.repositories import ReportRepository
from app.shared.application.ports import StoragePort


class CreateReport:
    def __init__(self, report_repo: ReportRepository) -> None:
        self._report_repo = report_repo

    def execute(
        self,
        company_id: UUID,
        title: str,
        report_type: ReportType,
        params: dict[str, Any],
    ) -> ReportDTO:
        entity = Report(
            company_id=company_id,
            title=title,
            report_type=report_type,
            params=params,
        )
        saved = self._report_repo.add(entity)
        return ReportDTO.from_entity(saved)


class GenerateReport:
    """Builds real report content from the DSS data and saves it via StoragePort.

    Content depends on the report type: a forecast report summarizes the latest
    successful FTGM run (per-product model, order and accuracy), a KPI report the
    latest KPI values, and a recommendation report the pending replenishments. The
    cross-module repositories are optional so the use case still works (with a note)
    when a data source is unavailable.
    """

    def __init__(
        self,
        report_repo: ReportRepository,
        storage: StoragePort,
        *,
        runs: ForecastRunRepository | None = None,
        metrics: ForecastMetricsRepository | None = None,
        kpis: KpiRepository | None = None,
        recommendations: RecommendationRepository | None = None,
        products: ProductRepository | None = None,
    ) -> None:
        self._report_repo = report_repo
        self._storage = storage
        self._runs = runs
        self._metrics = metrics
        self._kpis = kpis
        self._recommendations = recommendations
        self._products = products

    def execute(self, company_id: UUID, report_id: UUID) -> ReportDTO:
        entity = self._report_repo.get_by_id(report_id)
        if not entity or entity.company_id != company_id:
            raise ReportNotFoundError(report_id)

        try:
            content_dict: dict[str, Any] = {
                "report_id": str(entity.id),
                "title": entity.title,
                "type": entity.report_type.value,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "company_id": str(company_id),
            }
            content_dict.update(self._build_content(company_id, entity.report_type))

            content_bytes = json.dumps(content_dict, indent=2, ensure_ascii=False).encode("utf-8")
            file_name = f"report_{entity.id}.json"
            file_path = self._storage.save(file_name, content_bytes, "application/json")

            entity.mark_ready(file_path)
            self._report_repo.update(entity)
        except Exception:
            entity.mark_failed()
            self._report_repo.update(entity)
            raise

        return ReportDTO.from_entity(entity)

    # ------------------------------------------------------------------ content
    def _sku_map(self, company_id: UUID) -> dict[UUID, dict[str, str]]:
        if self._products is None:
            return {}
        return {
            p.id: {"sku": p.sku.value if hasattr(p.sku, "value") else str(p.sku), "name": p.name}
            for p in self._products.list_active(company_id)
            if p.id is not None
        }

    def _build_content(self, company_id: UUID, report_type: ReportType) -> dict[str, Any]:
        if report_type == ReportType.FORECAST:
            return self._forecast_content(company_id)
        if report_type == ReportType.KPI:
            return self._kpi_content(company_id)
        if report_type == ReportType.RECOMMENDATION:
            return self._recommendation_content(company_id)
        return {"note": "Tipo de reporte no reconocido."}

    def _forecast_content(self, company_id: UUID) -> dict[str, Any]:
        if self._runs is None or self._metrics is None:
            return {"note": "Fuente de pronóstico no disponible."}
        run = next(
            (
                r
                for r in self._runs.list_by_company(company_id, 0, 50)
                if r.status == RunStatus.SUCCESS and not r.is_backtest
            ),
            None,
        )
        if run is None or run.id is None:
            return {"note": "Aún no hay un pronóstico completado."}
        skus = self._sku_map(company_id)
        rows = [
            {
                "sku": skus.get(m.product_id, {}).get("sku", str(m.product_id)[:8]),
                "producto": skus.get(m.product_id, {}).get("name", ""),
                "modelo": m.model_used,
                "orden_fourier": m.order_selected,
                "estado": m.status,
                "mape": float(m.mape) if m.mape is not None else None,
                "mase": float(m.mase) if m.mase is not None else None,
                "rmsse": float(m.rmsse) if m.rmsse is not None else None,
            }
            for m in self._metrics.list_by_run(run.id)
        ]
        meta = run.meta
        return {
            "run_id": str(run.id),
            "alcance": meta.get("description") or "Dataset preparado",
            "fecha_corte": meta.get("as_of"),
            "frecuencia": run.frequency,
            "modelo": run.model_name,
            "horizonte_dias": run.horizon_days,
            "resumen": meta.get("summary"),
            "productos": len(rows),
            "detalle": rows,
        }

    def _kpi_content(self, company_id: UUID) -> dict[str, Any]:
        if self._kpis is None:
            return {"note": "Fuente de KPIs no disponible."}
        skus = self._sku_map(company_id)
        # Keep the latest value per (product, kpi type).
        latest: dict[tuple[UUID, str], Any] = {}
        for k in self._kpis.list_by_company(company_id, 0, 1000):
            key = (k.product_id, k.kpi_type.value)
            prev = latest.get(key)
            if prev is None or k.computed_at > prev.computed_at:
                latest[key] = k
        rows = [
            {
                "sku": skus.get(k.product_id, {}).get("sku", str(k.product_id)[:8]),
                "producto": skus.get(k.product_id, {}).get("name", ""),
                "indicador": k.kpi_type.value,
                "valor": float(k.value),
            }
            for k in latest.values()
        ]
        return {"total_indicadores": len(rows), "detalle": rows}

    def _recommendation_content(self, company_id: UUID) -> dict[str, Any]:
        if self._recommendations is None:
            return {"note": "Fuente de recomendaciones no disponible."}
        skus = self._sku_map(company_id)
        rows = [
            {
                "sku": skus.get(r.product_id, {}).get("sku", str(r.product_id)[:8]),
                "producto": skus.get(r.product_id, {}).get("name", ""),
                "cantidad_sugerida": r.recommended_quantity.value,
                "prioridad": r.priority.value,
                "estado": r.status.value,
                "motivo": r.reason,
            }
            for r in self._recommendations.list_by_company(company_id, 0, 1000)
        ]
        return {"total_recomendaciones": len(rows), "detalle": rows}


class ListReports:
    def __init__(self, report_repo: ReportRepository) -> None:
        self._report_repo = report_repo

    def execute(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[ReportDTO]:
        entities = self._report_repo.list_by_company(
            company_id=company_id, offset=offset, limit=limit
        )
        return [ReportDTO.from_entity(e) for e in entities]


class GetReport:
    def __init__(self, report_repo: ReportRepository) -> None:
        self._report_repo = report_repo

    def execute(self, company_id: UUID, report_id: UUID) -> ReportDTO:
        entity = self._report_repo.get_by_id(report_id)
        if not entity or entity.company_id != company_id:
            raise ReportNotFoundError(report_id)
        return ReportDTO.from_entity(entity)


class DownloadReport:
    """Returns the bytes, filename, and content_type of a generated report."""

    def __init__(self, report_repo: ReportRepository, storage: StoragePort) -> None:
        self._report_repo = report_repo
        self._storage = storage

    def execute(self, company_id: UUID, report_id: UUID) -> tuple[bytes, str, str]:
        entity = self._report_repo.get_by_id(report_id)
        if not entity or entity.company_id != company_id:
            raise ReportNotFoundError(report_id)

        if not entity.file_path:
            raise ValueError("Report is not ready or has no file_path")

        content = self._storage.get(entity.file_path)
        file_name = f"report_{entity.id}.json"
        content_type = "application/json"

        return content, file_name, content_type
