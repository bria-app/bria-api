"""Mock FTGM adapter — demo predictions without the deployed engine.

Set ``FTGM_ENGINE_MODE=mock`` and forecast runs never call the engine service:
this adapter produces the full engine contract (points with bounds, cleaned history,
metrics, tournament diagnostics) locally, so every screen works exactly the same.

It is *data-aware*, not canned: the forecast level comes from the product's own recent
sales, so any product of any inventory gets a sensible, readable prediction. A small
dictionary of sentinel product names (one per demo profile, e.g. «iPhone 15 Pro Max»)
detects which business profile is loaded and flavours the numbers and the narrative
(seasonality shape, growth, band width) accordingly.

Honesty rule (audit C-04): the mock never *fabricates measurements*. It produces a
simulated projection, but no accuracy, no competing candidates, no skill vs naive and
no MAPE/MAE/RMSE/MASE/RMSSE — those fields are ``None``/empty — and it labels its model
``"DEMO"`` (never "FTGM") with ``diagnostics.engine == "mock"`` so every screen can show
the demo banner.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data_preparation.domain.entities import PreparedTimeSeries
from app.modules.data_preparation.infrastructure.erp_source import lima_today
from app.modules.forecasting.application.ports import ProductForecast
from app.modules.forecasting.domain.value_objects import ForecastPoint, HistoryPoint
from app.modules.products.infrastructure.persistence.models import ProductModel

# ── Demo profiles ────────────────────────────────────────────────────────────
# Sentinel (lowercase substring of a product name) → profile. The generated demo
# spreadsheets each contain exactly one of these products.
SENTINELS: dict[str, str] = {
    "oud royal": "perfumes",
    "esencia de caracol": "skincare",
    "casaca vintage levi": "vintage",
    "iphone 15 pro max": "apple",
    "oxford cuero": "calzado",
}

# Fallback detection when the sentinel was renamed or removed: score the whole catalogue
# against each profile's vocabulary and take the best one (≥ _FINGERPRINT_MIN hits). This
# also recognises a real shop that never saw the demo spreadsheets.
_FINGERPRINTS: dict[str, tuple[str, ...]] = {
    "perfumes": ("oud", "perfume", "fragancia", "lattafa", "ml", "eau de", "attar", "almizcle", "decant"),
    "skincare": ("serum", "sérum", "esencia", "crema", "mascarilla", "tónico", "tonico", "spf", "niacinamida", "retinol", "limpiador"),
    "vintage": ("vintage", "casaca", "jean", "polo", "camisa", "chompa", "falda", "denim", "franela"),
    "apple": ("iphone", "ipad", "macbook", "airpods", "apple watch", "magsafe", "usb-c", "case"),
    "calzado": ("oxford", "derby", "botín", "botin", "mocasín", "mocasin", "zapatilla", "loafer", "cuero", "chelsea"),
}
_FINGERPRINT_MIN = 2

# Per-profile flavour: month multipliers (Jan..Dec), yearly growth, band-width range and
# the sentence the result screen shows as the model's explanation.
_PROFILES: dict[str, dict[str, Any]] = {
    "perfumes": {
        "season": [0.9, 1.05, 0.9, 0.85, 1.1, 0.95, 1.0, 0.95, 0.9, 1.0, 1.15, 1.45],
        "growth": 0.14,
        "acc": (78, 88),
        "story": "Tus perfumes tienen picos claros en diciembre y fechas especiales (Día de la Madre, San Valentín); la IA proyecta ese patrón.",
    },
    "skincare": {
        "season": [1.05, 1.0, 0.95, 0.9, 0.95, 1.0, 1.05, 1.0, 1.0, 1.05, 1.15, 1.3],
        "growth": 0.22,
        "acc": (76, 86),
        "story": "El skincare coreano viene creciendo de forma sostenida, con empuje extra en campañas y fin de año.",
    },
    "vintage": {
        "season": [1.0, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.05, 1.0, 1.0, 1.05, 1.15],
        "growth": 0.06,
        "acc": (68, 78),
        "story": "La ropa vintage se mueve por piezas únicas: la IA proyecta el ritmo del negocio más que unidades exactas por prenda.",
    },
    "apple": {
        "season": [0.9, 0.85, 0.9, 0.95, 1.0, 1.0, 1.2, 0.95, 1.25, 1.1, 1.2, 1.4],
        "growth": 0.10,
        "acc": (79, 89),
        "story": "Los productos Apple se disparan con lanzamientos (septiembre) y campañas de julio y diciembre; la IA sigue ese calendario.",
    },
    "calzado": {
        "season": [0.9, 0.9, 0.95, 1.05, 1.15, 1.1, 1.2, 1.0, 0.95, 1.0, 1.1, 1.3],
        "growth": 0.08,
        "acc": (72, 84),
        "story": "El calzado de cuero sube con el frío (mayo–julio) y en diciembre; la IA proyecta esa estacionalidad.",
    },
    "general": {
        "season": [0.95, 0.95, 1.0, 1.0, 1.05, 1.0, 1.05, 1.0, 1.0, 1.0, 1.1, 1.3],
        "growth": 0.08,
        "acc": (72, 85),
        "story": "La IA proyecta el ritmo reciente de tus ventas con el empuje típico de fin de año del retail peruano.",
    },
}

#: Model label of every mock result: the demo must never be attributed to the FTGM.
MOCK_MODEL = "DEMO"

# Shown on every result produced by the demo engine (never by the real one).
MOCK_NOTICE = "MODO DEMOSTRACIÓN — cifras simuladas, no provienen del motor FTGM."


def profile_name_for(names: list[str]) -> str:
    """Which demo profile a catalogue belongs to (lowercase product names)."""
    for sentinel, profile in SENTINELS.items():
        if any(sentinel in n for n in names):
            return profile
    scores = {
        profile: sum(1 for kw in words if any(kw in n for n in names))
        for profile, words in _FINGERPRINTS.items()
    }
    best = max(scores, key=lambda p: scores[p])
    return best if scores[best] >= _FINGERPRINT_MIN else "general"


def _seed(product_id: Any, salt: str = "") -> float:
    """Deterministic 0..1 per product: same product, same demo numbers, every run."""
    digest = hashlib.md5(f"{product_id}{salt}".encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class MockFtgmAdapter:
    """Drop-in replacement for FtgmHttpAdapter (same ``forecast`` signature)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # -- profile detection ---------------------------------------------------
    def _profile_for(self, series: list[PreparedTimeSeries]) -> dict[str, Any]:
        """Sentinel product first (the documented switch), then a catalogue fingerprint."""
        ids = [s.product_id for s in series]
        names = [
            (n or "").lower()
            for n in self._session.execute(
                select(ProductModel.name).where(ProductModel.id.in_(ids))
            ).scalars()
        ]
        return _PROFILES[profile_name_for(names)]

    # -- main entry ----------------------------------------------------------
    def forecast(
        self,
        *,
        series: list[PreparedTimeSeries],
        horizon_days: int,
        model_name: str,
        frequency: str | None = None,
        as_of: date | None = None,
    ) -> list[ProductForecast]:
        profile = self._profile_for(series)
        cutoff = as_of or lima_today()
        return [self._one(s, horizon_days, frequency or "auto", cutoff, profile) for s in series]

    def _one(
        self,
        s: PreparedTimeSeries,
        horizon_days: int,
        frequency: str,
        as_of: date,
        profile: dict[str, Any],
    ) -> ProductForecast:
        daily = {p.period_date: float(p.demand) for p in s.points}
        span_days = (max(daily) - min(daily)).days + 1 if daily else 0
        weekly = frequency == "weekly" or (frequency == "auto" and span_days <= 430)
        step = 7 if weekly else 30
        freq_label = "weekly" if weekly else "monthly"

        # Bucket the sparse daily sales into closed periods ending at the cut-off.
        n_hist = max(6, min(52 if weekly else 24, span_days // step))
        buckets: list[tuple[date, float]] = []
        for i in range(n_hist, 0, -1):
            b_start = as_of - timedelta(days=step * i)
            b_end = b_start + timedelta(days=step)
            units = sum(u for d, u in daily.items() if b_start <= d < b_end)
            buckets.append((b_start, units))

        values = [u for _, u in buckets]
        # Level: exponentially-weighted recent average (last periods matter most).
        weights = [0.85 ** (len(values) - 1 - i) for i in range(len(values))]
        level = sum(v * w for v, w in zip(values, weights)) / (sum(weights) or 1.0)
        recent = sum(values[-4:]) / max(1, len(values[-4:]))

        # How fast the product really moves. Everything downstream (forecast shape and the
        # advice the screens show) has to stay consistent with this: something that sold 6
        # units in a year can never end up with an aggressive restock suggestion, and
        # something selling 150 a month must not be under-forecast into a stock-out.
        total_units = sum(values)
        months = max(1.0, (step * len(values)) / 30.44)
        per_month = total_units / months
        rotation = "baja" if (per_month < 2.0 or total_units < 10) else "alta" if per_month >= 40 else "media"

        # Width of the simulated band only (never reported as an accuracy).
        acc_lo, acc_hi = profile["acc"]
        band_ref = acc_lo + (acc_hi - acc_lo) * _seed(s.product_id)
        season: list[float] = profile["season"]
        growth = float(profile["growth"]) * (0.7 + 0.6 * _seed(s.product_id, "g"))
        per_period_growth = growth / (52 if weekly else 12)

        # History with a smooth "fitted" line (what the chart draws as the model fit).
        history: list[HistoryPoint] = []
        for i, (d, u) in enumerate(buckets):
            lo = max(0, i - 2)
            fitted = sum(values[lo : i + 1]) / (i + 1 - lo)
            history.append(
                HistoryPoint(
                    period_date=d,
                    observed=Decimal(str(round(u, 2))),
                    cleaned=Decimal(str(round(u, 2))),
                    fitted=Decimal(str(round(fitted, 2))),
                    is_stockout=False,
                    is_outlier=False,
                )
            )

        # Forecast: level × seasonal shape × gentle growth, ± a simulated band.
        # Slow movers get no growth and no seasonal amplification (a product that barely
        # sells does not suddenly triple); fast movers are floored at their recent pace.
        base_level = level
        if rotation == "baja":
            per_period_growth = 0.0
        elif rotation == "alta":
            base_level = max(level, recent)
        n_fc = max(1, round(horizon_days / step))
        spread = (100.0 - band_ref) / 100.0 + 0.08
        points: list[ForecastPoint] = []
        prev = float(values[-1]) if values else base_level
        for k in range(1, n_fc + 1):
            d = as_of + timedelta(days=step * (k - 1))
            mult = min(1.0, season[d.month - 1]) if rotation == "baja" else season[d.month - 1]
            value = max(0.0, base_level * mult * (1 + per_period_growth * k))
            if rotation == "baja":
                value = min(value, base_level)
            # No jump out of the gate: the first forecast period leans on the last observed
            # one, so the chart line continues instead of breaking.
            if k == 1:
                value = 0.45 * prev + 0.55 * value
            points.append(
                ForecastPoint(
                    period_date=d,
                    predicted_demand=Decimal(str(round(value, 2))),
                    lower_bound=Decimal(str(round(max(0.0, value * (1 - spread)), 2))),
                    upper_bound=Decimal(str(round(value * (1 + spread), 2))),
                )
            )

        fc_rate = float(points[0].predicted_demand) if points else 0.0
        trend_pct = round((fc_rate / recent - 1) * 100, 1) if recent > 0 else None

        per_unit = "semana" if weekly else "mes"
        if rotation == "baja":
            rotation_note = (
                f"Rotación baja: {round(total_units)} unidades en {round(months)} meses "
                f"(≈{per_month:.1f} al mes). Mantén stock bajo: no conviene reponer."
            )
            advice = "no_reponer"
        elif rotation == "alta":
            rotation_note = (
                f"Rotación alta: ≈{per_month:.0f} unidades al mes y {fc_rate:.0f} previstas "
                f"para la próxima {per_unit}. Prioriza la reposición para no quebrar stock."
            )
            advice = "reponer_prioritario"
        else:
            rotation_note = f"Rotación estable: ≈{per_month:.1f} unidades al mes."
            advice = "normal"

        diagnostics: dict[str, Any] = {
            "frequency": freq_label,
            # Nothing was validated: no accuracy, no hold-out, no tournament.
            "accuracy_pct": None,
            "forecast_vs_recent_pct": trend_pct,
            # The demo engine identifies itself so the screens can label the result.
            "engine": "mock",
            "mock_notice": MOCK_NOTICE,
            "rotation": rotation,
            "units_per_month": round(per_month, 2),
            "advice": advice,
            "explanation": profile["story"],
            "explanations": [profile["story"], rotation_note],
            "holdout": None,
            "skill_vs_naive": None,
            "candidates": [],
        }

        return ProductForecast(
            product_id=s.product_id,
            points=points,
            history=history,
            mape=None,
            mae=None,
            rmse=None,
            mase=None,
            rmsse=None,
            order_selected=0,
            model_used=MOCK_MODEL,
            status="ok" if total_units > 0 else "fallback",
            fallback_reason=None if total_units > 0 else "Sin ventas suficientes en el periodo analizado.",
            validation_rmse=None,
            frequency=freq_label,
            period=52 if weekly else 12,
            warnings=[],
            diagnostics=diagnostics,
        )
