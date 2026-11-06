"""Reports module — HTTP schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.modules.reports.application.dtos import ReportDTO
from app.modules.reports.domain.enums import ReportType


class ReportResponse(ReportDTO):
    """Response schema for a report."""
    pass


class CreateReportRequest(BaseModel):
    """Request schema for creating a report."""
    title: str = Field(..., min_length=1, max_length=255)
    report_type: ReportType
    params: dict[str, Any] = Field(default_factory=dict)


# Placeholders for endpoints not fully implemented
class ReportStatusResponse(BaseModel):
    message: str
    module: str
    action: str

class ReportTemplateResponse(BaseModel):
    message: str
    module: str
    action: str
