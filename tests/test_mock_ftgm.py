"""Profile detection and rotation coherence of the demo (mock) FTGM engine."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.forecasting.infrastructure.adapters.mock_ftgm import (
    MOCK_NOTICE,
    MockFtgmAdapter,
    SENTINELS,
    _PROFILES,
    profile_name_for,
)

TODAY = date(2026, 9, 20)


class _Point:
    def __init__(self, day: date, qty: float) -> None:
        self.period_date = day
        self.demand = Decimal(str(qty))


class _Series:
    def __init__(self, product_id: str, events: list[tuple[int, float]]) -> None:
        self.product_id = product_id
        self.points = [_Point(TODAY - timedelta(days=d), q) for d, q in events]


def _forecast(events, horizon=30):
    return MockFtgmAdapter(None)._one(_Series("p", events), horizon, "auto", TODAY, _PROFILES["general"])


@pytest.mark.parametrize(
    "names,expected",
    [
        # Level 1: the documented sentinel switches the profile on its own.
        (["iPhone 15 Pro Max 256GB", "cable usb-c"], "apple"),
        (["Oud Royal Intense 100ml"], "perfumes"),
        (["Esencia de Caracol Premium 96%"], "skincare"),
        (["Casaca Vintage Levi's 90s"], "vintage"),
        (["Oxford Cuero Marrón Clásico"], "calzado"),
        # Level 2: sentinel renamed or left out — the catalogue fingerprint still lands.
        (["iphone 13 128gb", "airpods pro", "cargador magsafe"], "apple"),
        (["zapato derby negro", "botín chelsea camel", "mocasín penny loafer"], "calzado"),
        (["serum niacinamida", "mascarilla hidrogel", "protector solar spf50"], "skincare"),
        (["casaca cuero 90s", "jean wrangler recto", "camisa franela grunge"], "vintage"),
        # A real shop that looks like none of them keeps the generic retail profile.
        (["arroz costeño 5kg", "aceite primor 1l", "leche gloria"], "general"),
        (["cuaderno rayado"], "general"),
        ([], "general"),
    ],
)
def test_profile_detection(names, expected):
    assert profile_name_for([n.lower() for n in names]) == expected


def test_every_sentinel_maps_to_a_profile():
    for profile in SENTINELS.values():
        assert profile in _PROFILES


def test_slow_mover_never_gets_an_aggressive_restock():
    """6 sales in a year: the horizon total must stay under one unit (→ 'descontinuar')."""
    f = _forecast([(350, 1), (300, 1), (240, 1), (160, 1), (90, 1), (20, 1)])
    assert f.diagnostics["rotation"] == "baja"
    assert f.diagnostics["advice"] == "no_reponer"
    assert sum(float(p.predicted_demand) for p in f.points) < 1.0
    assert "no conviene reponer" in f.diagnostics["explanations"][1]


def test_fast_mover_keeps_its_pace_and_is_prioritised():
    """~150 units a month: the forecast must not collapse below the recent pace."""
    f = _forecast([(d, 5) for d in range(1, 181)])
    assert f.diagnostics["rotation"] == "alta"
    assert f.diagnostics["advice"] == "reponer_prioritario"
    per_period = float(f.points[0].predicted_demand)
    assert per_period >= 0.8 * float(f.history[-1].observed)


@pytest.mark.parametrize(
    "events",
    [
        [(d, 5) for d in range(1, 181)],
        [(d, 2) for d in range(1, 181, 3)],
        [(350, 1), (300, 1), (240, 1), (160, 1), (90, 1), (20, 1)],
    ],
)
def test_forecast_continues_from_the_last_observed_period(events):
    """No jump between the last real period and the first projected one."""
    f = _forecast(events)
    last = float(f.history[-1].observed)
    first = float(f.points[0].predicted_demand)
    assert abs(first - last) <= max(1.0, 0.6 * max(last, first))


def test_every_mock_result_carries_the_notice():
    f = _forecast([(d, 3) for d in range(1, 120)])
    assert f.diagnostics["engine"] == "mock"
    assert f.diagnostics["mock_notice"] == MOCK_NOTICE
