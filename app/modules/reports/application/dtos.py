"""Reports module — application DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.enums import ReportStatus, ReportType


class ReportDTO(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    report_type: ReportType
    status: ReportStatus
    file_path: str | None
    params: dict[str, Any]
    #: When it was asked for; None only for rows not yet stored.
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, entity: Report) -> ReportDTO:
        if entity.id is None:
            raise ValueError("Entity must have an id to create DTO")
        return cls(
            id=entity.id,
            company_id=entity.company_id,
            title=entity.title,
            report_type=entity.report_type,
            status=entity.status,
            file_path=entity.file_path,
            params=entity.params,
            created_at=entity.created_at,
        )
