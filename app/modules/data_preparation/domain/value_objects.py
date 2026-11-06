"""Data preparation module domain — value objects."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class SeriesPoint:
    """A single data point in a prepared time series."""

    period_date: date
    demand: Decimal
    is_stockout: bool = False


@dataclass(frozen=True)
class RawDemandRow:
    """A row parsed from an ingested file, before product resolution.

    ``sku`` is the product identifier as it appears in the file.
    """

    sku: str
    period_date: date
    quantity: Decimal
    is_stockout: bool = False


@dataclass(frozen=True)
class DemandRecord:
    """A demand observation with the product already resolved to its UUID."""

    product_id: UUID
    period_date: date
    quantity: Decimal
    is_stockout: bool = False
