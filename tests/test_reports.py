"""Tests for Reports module."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.reports.application.use_cases.report import (
    CreateReport,
    DownloadReport,
    GenerateReport,
    GetReport,
)
from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.enums import ReportStatus, ReportType
from app.modules.reports.domain.exceptions import ReportNotFoundError
from tests.test_files import FakeStoragePort


class FakeReportRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Report] = {}

    def get_by_id(self, report_id: UUID) -> Report | None:
        return self._store.get(report_id)

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Report]:
        rows = [r for r in self._store.values() if r.company_id == company_id]
        return rows[offset : offset + limit]

    def add(self, report: Report) -> Report:
        if report.id is None:
            report.id = uuid4()
        self._store[report.id] = report
        return report

    def update(self, report: Report) -> Report:
        assert report.id is not None
        self._store[report.id] = report
        return report

    def delete(self, report_id: UUID) -> bool:
        return self._store.pop(report_id, None) is not None


class TestReportUseCases:
    def test_create_and_generate_report(self) -> None:
        repo = FakeReportRepository()
        storage = FakeStoragePort()
        company_id = uuid4()

        # Create
        created = CreateReport(repo).execute(
            company_id=company_id,
            title="Sales KPI",
            report_type=ReportType.KPI,
            params={"month": "2026-06"},
        )
        assert created.status == ReportStatus.PENDING

        # Generate
        generated = GenerateReport(repo, storage).execute(
            company_id=company_id, report_id=created.id
        )
        assert generated.status == ReportStatus.READY
        assert generated.file_path is not None

        # Verify storage
        content = storage.get(generated.file_path)
        assert b'"report_id"' in content and b'"type": "kpi"' in content

    def test_download_report(self) -> None:
        repo = FakeReportRepository()
        storage = FakeStoragePort()
        company_id = uuid4()

        created = CreateReport(repo).execute(
            company_id=company_id,
            title="Forecast 1",
            report_type=ReportType.FORECAST,
            params={},
        )
        GenerateReport(repo, storage).execute(company_id=company_id, report_id=created.id)

        content, file_name, mime = DownloadReport(repo, storage).execute(
            company_id=company_id, report_id=created.id
        )
        assert content.startswith(b"{")
        assert mime == "application/json"
        assert file_name == f"report_{created.id}.json"

    def test_get_unknown_report_raises(self) -> None:
        repo = FakeReportRepository()
        with pytest.raises(ReportNotFoundError):
            GetReport(repo).execute(company_id=uuid4(), report_id=uuid4())
