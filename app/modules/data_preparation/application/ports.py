"""Data preparation module — application ports."""
from __future__ import annotations

from typing import Protocol

from app.modules.data_preparation.domain.value_objects import RawDemandRow
from app.modules.ingestion.domain.enums import FileType


class DemandRowParser(Protocol):
    """Turns an ingested file into raw demand rows (adapter: ``file_parser.parse_demand_rows``)."""

    def __call__(
        self, *, content: bytes, file_type: FileType, column_mapping: dict[str, str]
    ) -> list[RawDemandRow]: ...
