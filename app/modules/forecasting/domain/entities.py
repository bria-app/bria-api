"""Forecasting module domain — entities.

ForecastRun implements a state machine with the following valid transitions:
    PENDING  → RUNNING   (start)
    PENDING  → CANCELLED (cancel)
    RUNNING  → SUCCESS   (complete)
    RUNNING  → FAILED    (fail)
    RUNNING  → CANCELLED (cancel)

Any other transition raises InvalidRunTransitionError.

Design note: ForecastMetrics is modeled as a standalone entity (not a frozen VO)
because it has an identity (run_id + product_id), is persisted independently, and
may be queried/listed on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.forecasting.domain.enums import RunStatus
from app.modules.forecasting.domain.exceptions import InvalidRunTransitionError
from app.modules.forecasting.domain.value_objects import ForecastPoint, HistoryPoint


# Valid state transitions for ForecastRun
_VALID_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset({RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.SUCCESS: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


@dataclass
class ForecastRun:
    """A forecast execution run tracking its lifecycle."""

    company_id: UUID
    model_name: str
    horizon_days: int
    dataset_id: UUID | None = None
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    id: UUID | None = None
    # How the run was scoped ({"type": "recent_sales", "months": 12, ...}); the engine's
    # per-product diagnostics and the run summary live under scope["_meta"].
    scope: dict[str, Any] | None = None
    product_ids: list[str] | None = None
    frequency: str | None = None
    created_at: datetime | None = None

    @property
    def meta(self) -> dict[str, Any]:
        return dict((self.scope or {}).get("_meta") or {})

    @property
    def is_backtest(self) -> bool:
        """A test against the past (cut-off before the day it was asked): it checks the model,
        so it must never feed today's decisions (latest forecast, recommendations, KPIs)."""
        return bool(self.meta.get("backtest"))

    def set_meta(self, **values: Any) -> None:
        scope = dict(self.scope or {"type": "dataset"})
        meta = dict(scope.get("_meta") or {})
        meta.update(values)
        scope["_meta"] = meta
        self.scope = scope

    def _transition(self, target: RunStatus) -> None:
        """Validate and perform a state transition."""
        allowed = _VALID_TRANSITIONS.get(self.status, frozenset())
        if target not in allowed:
            raise InvalidRunTransitionError(
                message=(
                    f"El pronóstico no puede pasar de «{self.status}» a «{target}»."
                )
            )
        self.status = target

    def start(self) -> None:
        """Mark the run as started."""
        self._transition(RunStatus.RUNNING)
        self.started_at = datetime.now(timezone.utc)

    def complete(self) -> None:
        """Mark the run as successfully completed."""
        self._transition(RunStatus.SUCCESS)
        self.completed_at = datetime.now(timezone.utc)

    def fail(self, message: str) -> None:
        """Mark the run as failed with an error message."""
        self._transition(RunStatus.FAILED)
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = message

    def cancel(self) -> None:
        """Cancel the run."""
        self._transition(RunStatus.CANCELLED)
        self.completed_at = datetime.now(timezone.utc)


@dataclass
class ForecastResult:
    """Forecast output for a single product within a run."""

    run_id: UUID
    company_id: UUID
    product_id: UUID
    points: list[ForecastPoint] = field(default_factory=list)
    # In-sample history (observed/cleaned/fitted per bucket) as returned by the engine.
    history: list[HistoryPoint] = field(default_factory=list)
    id: UUID | None = None


@dataclass
class ForecastMetrics:
    """Accuracy metrics + model provenance for a forecast run on a specific product.

    ``model_used`` records which model actually produced the forecast ("FTGM" or the
    "SeasonalNaive" fallback) and ``order_selected`` the Fourier order chosen by
    Algorithm 1 (0 = baseline). ``status`` mirrors the engine's per-product outcome
    (ok / fallback / skipped) with ``fallback_reason`` explaining why.
    """

    run_id: UUID
    product_id: UUID
    # None = the engine could not measure it (e.g. MAPE when every actual is 0) — never 0.
    mape: Decimal | None
    mae: Decimal | None
    rmse: Decimal | None
    mase: Decimal | None = None
    rmsse: Decimal | None = None
    order_selected: int = 0
    model_used: str = ""
    status: str = "ok"
    fallback_reason: str | None = None
    validation_rmse: Decimal | None = None
