"""Business rules the acceptance criteria promise, each pinned at its boundary.

A rule here failed nobody when it was changed before these tests existed: the free plan's limit,
the seller's reach, the reorder window. Each test would fail if its rule moved.
"""
from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.data_preparation.domain.erp_analysis import (
    LEDGER_CONSISTENCY,
    ProductHistory,
    detect_stockouts,
)
from app.modules.kpis.domain.services import ProductKpiInputs, overstock_risk, stockout_risk
from app.modules.recommendations.domain.services import (
    DEFAULT_LEAD_TIME_DAYS,
    SAFETY_MARGIN_DAYS,
    ReorderInputs,
    suggest_reorder,
)
from tests.test_audit_fixes import API, _create_user, _register, client, db_factory  # noqa: F401

_ = (client, db_factory)


def _daily(value: int, days: int) -> list[Decimal]:
    return [Decimal(value)] * days


# --- The seller stays in the till (HU0005) ------------------------------------------------------
@pytest.mark.parametrize(
    "module",
    ["forecast-runs", "purchases", "suppliers", "reports", "kpis", "recommendations", "users"],
)
def test_seller_cannot_read_modules_outside_the_till(client: TestClient, module: str) -> None:  # noqa: F811
    headers, company_id, _owner = _register(client, "s1", "20111111101")
    _, seller = _create_user(client, headers, company_id, "caja1", "seller")
    res = client.get(f"{API}/companies/{company_id}/{module}", headers=seller)
    assert res.status_code == 403, res.text
    assert "ventas" in res.json()["message"]


def test_seller_reads_products_and_stock_without_costs(client: TestClient) -> None:  # noqa: F811
    headers, company_id, _owner = _register(client, "s2", "20111111102")
    _, seller = _create_user(client, headers, company_id, "caja2", "seller")
    base = f"{API}/companies/{company_id}"
    created = client.post(
        f"{base}/products",
        headers=headers,
        json={"name": "Polo", "unit_price": "10", "unit_cost": "4", "initial_stock": 5},
    )
    assert created.status_code == 201, created.text

    product = client.get(f"{base}/products/{created.json()['id']}", headers=seller)
    assert product.status_code == 200
    assert product.json()["unit_cost"] is None

    overview = client.get(f"{base}/inventory/overview", headers=seller)
    assert overview.status_code == 200
    body = overview.json()
    items = body["items"] if isinstance(body, dict) else body
    assert items[0]["unit_cost"] is None


# --- Three forecasts a month on the free plan, on the route the web uses (HU0037) ---------------
def _quota_company(
    client: TestClient,  # noqa: F811
    factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tax_id: str,
    runs: int,
) -> tuple[dict[str, str], str]:
    from app.modules.forecasting.domain.entities import ForecastRun
    from app.modules.forecasting.infrastructure.persistence.repositories import SqlForecastRunRepository
    import app.modules.forecasting.presentation.router as forecast_router

    monkeypatch.setattr(forecast_router, "run_forecast_job", lambda *a, **k: None)
    headers, company_id, _owner = _register(client, tax_id[-4:], tax_id)
    with factory() as session:
        repo = SqlForecastRunRepository(session)
        for _i in range(runs):
            repo.add(ForecastRun(company_id=UUID(company_id), model_name="FTGM", horizon_days=30, dataset_id=None))
        session.commit()
    return headers, company_id


def _new_run(client: TestClient, headers: dict[str, str], company_id: str):  # noqa: F811, ANN202
    return client.post(
        f"{API}/companies/{company_id}/forecast-runs",
        headers=headers,
        json={"scope": {"type": "all"}, "horizon_days": 30},
    )


def test_free_plan_allows_a_third_forecast(
    client: TestClient, db_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    headers, company_id = _quota_company(client, db_factory, monkeypatch, "20111111103", runs=2)
    # No products yet, so it stops further on: what matters is that the plan let it through.
    assert _new_run(client, headers, company_id).status_code != 403


def test_free_plan_refuses_a_fourth_forecast(
    client: TestClient, db_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    headers, company_id = _quota_company(client, db_factory, monkeypatch, "20111111104", runs=3)
    res = _new_run(client, headers, company_id)
    assert res.status_code == 403, res.text
    assert res.json()["details"]["monthly_limit"] == 3
    assert res.json()["details"]["used"] == 3


def test_failed_forecasts_do_not_count(
    client: TestClient, db_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    from app.modules.forecasting.infrastructure.persistence.models import ForecastRunModel

    headers, company_id = _quota_company(client, db_factory, monkeypatch, "20111111105", runs=3)
    with db_factory() as session:
        for run in session.query(ForecastRunModel).all():
            run.status = "failed"
        session.commit()
    assert _new_run(client, headers, company_id).status_code != 403


def test_preview_works_with_no_forecasts_left(
    client: TestClient, db_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    headers, company_id = _quota_company(client, db_factory, monkeypatch, "20111111106", runs=3)
    res = client.post(
        f"{API}/companies/{company_id}/forecast-runs/scope-preview",
        headers=headers,
        json={"scope": {"type": "all"}},
    )
    assert res.status_code == 200, res.text


# --- A ledger that doesn't explain the sales is not trusted (HU0020) ----------------------------
def _ledger(moved_out: int, sold: int) -> ProductHistory:
    start = date(2026, 1, 1)
    history = ProductHistory(product_id=uuid4())
    history.moves[start] = 100
    history.moves[start + timedelta(days=1)] = -moved_out
    history.sales[start + timedelta(days=1)] = sold
    return history


def test_ledger_explaining_half_the_sales_is_trusted() -> None:
    assert LEDGER_CONSISTENCY == 0.5
    assert detect_stockouts(_ledger(moved_out=5, sold=10), date(2026, 2, 1)).ledger_consistent


def test_ledger_explaining_less_than_half_is_not_trusted() -> None:
    assert not detect_stockouts(_ledger(moved_out=4, sold=10), date(2026, 2, 1)).ledger_consistent


def test_untrusted_ledger_uses_only_the_lost_sales_on_record() -> None:
    # Moves say the shelf went empty, but they explain too little of the sales to believe them.
    history = ProductHistory(product_id=uuid4())
    start = date(2026, 1, 1)
    history.moves[start] = 4
    history.moves[start + timedelta(days=1)] = -4
    history.sales[start + timedelta(days=1)] = 10
    asked = start + timedelta(days=20)
    history.lost[asked] = (1, 1)
    info = detect_stockouts(history, date(2026, 2, 1))
    assert not info.ledger_consistent
    assert info.days == {asked}


# --- How much to buy, and when (HU0028) ---------------------------------------------------------
def test_reorder_looks_at_the_wait_plus_two_weeks() -> None:
    assert SAFETY_MARGIN_DAYS == 14
    # 10 a day, 5 days of wait: 150 covers the wait (50) but not the wait + 14 days (190).
    suggestion = suggest_reorder(ReorderInputs(current_stock=150, daily_demand=_daily(10, 60), lead_time_days=5))
    assert suggestion is not None


def test_reorder_stays_quiet_once_that_window_is_covered() -> None:
    assert suggest_reorder(ReorderInputs(current_stock=190, daily_demand=_daily(10, 60), lead_time_days=5)) is None


def test_reorder_quantity_covers_the_wait_plus_a_month_by_default() -> None:
    suggestion = suggest_reorder(ReorderInputs(current_stock=150, daily_demand=_daily(10, 60), lead_time_days=5))
    assert suggestion is not None
    assert suggestion.quantity == 10 * (5 + 30) - 150


@pytest.mark.parametrize("lead", [0, None])
def test_missing_lead_time_counts_as_a_week_in_the_quantity(lead: int | None) -> None:
    assert DEFAULT_LEAD_TIME_DAYS == 7
    suggestion = suggest_reorder(
        ReorderInputs(current_stock=100, daily_demand=_daily(10, 60), lead_time_days=lead)  # type: ignore[arg-type]
    )
    assert suggestion is not None
    assert suggestion.quantity == 10 * (7 + 30) - 100


# --- Indicators count the safety stock (HU0027) -------------------------------------------------
def test_overstock_counts_the_safety_stock() -> None:
    demand = _daily(1, 130)
    inside = ProductKpiInputs(current_stock=150, daily_demand=demand, lead_time_days=5, safety_stock=50)
    assert overstock_risk(inside) == Decimal("0")
    over = ProductKpiInputs(current_stock=200, daily_demand=demand, lead_time_days=5, safety_stock=50)
    assert overstock_risk(over) == Decimal("15.00")


def test_stockout_risk_counts_the_safety_stock() -> None:
    # 190 covers the wait + two weeks, but not the 20 of safety stock on top.
    inp = ProductKpiInputs(current_stock=190, daily_demand=_daily(10, 60), lead_time_days=5, safety_stock=20)
    assert stockout_risk(inp) > Decimal("0")
    enough = ProductKpiInputs(current_stock=210, daily_demand=_daily(10, 60), lead_time_days=5, safety_stock=20)
    assert stockout_risk(enough) == Decimal("0")


# --- The stock the screens read goes down with a sale (HU0009) ----------------------------------
def test_stock_on_screen_goes_down_when_a_sale_goes_out(client: TestClient) -> None:  # noqa: F811
    headers, company_id, _owner = _register(client, "st", "20111111107")
    base = f"{API}/companies/{company_id}"
    product = client.post(
        f"{base}/products", headers=headers, json={"name": "Polo", "unit_price": "10", "initial_stock": 50}
    ).json()
    sold = client.post(
        f"{base}/sales-orders",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 3, "unit_price": "10"}]},
    )
    assert sold.status_code in (200, 201), sold.text
    overview = client.get(f"{base}/inventory/overview", headers=headers).json()
    items = overview["items"] if isinstance(overview, dict) else overview
    row = next(i for i in items if i.get("product_id", i.get("id")) == product["id"])
    assert row.get("on_hand", row.get("stock_on_hand")) == 47


# --- Old sales can't discount today's stock (HU0017) --------------------------------------------
def _import_rows(ages: list[int]) -> list[dict[str, str | int]]:
    today = date.today()
    return [
        {"row": i + 1, "name": "Polo azul", "sale_date": (today - timedelta(days=age)).isoformat(), "quantity": 1}
        for i, age in enumerate(ages)
    ]


@pytest.fixture()
def shop(client: TestClient) -> Generator[tuple[TestClient, dict[str, str], str], None, None]:  # noqa: F811
    headers, company_id, _owner = _register(client, "im", "20111111108")
    imported = client.post(
        f"{API}/companies/{company_id}/products/import",
        headers=headers,
        json={
            "rows": [{"row": 1, "name": "Polo azul", "unit_price": "25", "initial_stock": "30"}],
            "update_existing": True,
        },
    )
    assert imported.status_code == 200, imported.text
    yield client, headers, company_id


def _import(shop: tuple[TestClient, dict[str, str], str], ages: list[int]) -> int:
    http, headers, company_id = shop
    return http.post(
        f"{API}/companies/{company_id}/sales/import",
        headers=headers,
        json={"rows": _import_rows(ages), "affect_stock": True},
    ).status_code


def test_import_older_than_sixty_days_is_refused(shop: tuple[TestClient, dict[str, str], str]) -> None:
    assert _import(shop, [61, 61, 61]) == 422


def test_import_with_most_rows_old_is_refused_even_if_some_are_recent(
    shop: tuple[TestClient, dict[str, str], str],
) -> None:
    assert _import(shop, [61, 61, 61, 1]) == 422


def test_import_with_exactly_half_old_is_accepted(shop: tuple[TestClient, dict[str, str], str]) -> None:
    assert _import(shop, [61, 61, 1, 1]) == 201


def test_import_of_sixty_days_is_not_old(shop: tuple[TestClient, dict[str, str], str]) -> None:
    assert _import(shop, [60, 60, 60]) == 201


# --- Signing in says plainly what happened (HU0001) -----------------------------------------------
def test_login_gives_both_sessions(client: TestClient) -> None:  # noqa: F811
    _register(client, "l1", "20111111109")
    res = client.post(f"{API}/auth/login", json={"identifier": "ownerl1@tienda.pe", "password": "secret123"})
    assert res.status_code == 200, res.text
    assert res.json()["access_token"] and res.json()["refresh_token"]


def test_bad_login_says_it_plainly(client: TestClient) -> None:  # noqa: F811
    res = client.post(f"{API}/auth/login", json={"identifier": "nadie@test.pe", "password": "secret123"})
    assert res.status_code == 401
    assert res.json()["message"] == "Usuario o contraseña incorrectos"


def test_disabled_user_is_told_so(client: TestClient) -> None:  # noqa: F811
    headers, company_id, _owner = _register(client, "l2", "20111111110")
    user_id, _seller = _create_user(client, headers, company_id, "caja3", "seller")
    assert client.delete(f"{API}/companies/{company_id}/users/{user_id}", headers=headers).status_code in (200, 204)
    res = client.post(f"{API}/auth/login", json={"identifier": "caja3", "password": "secret123"})
    assert res.status_code == 403
    assert "desactivado" in res.json()["message"]


# --- Another company's path, with your own session (HU0005) ---------------------------------------
@pytest.mark.parametrize(
    "module",
    ["products", "inventory/overview", "sales", "sales-orders", "purchases", "suppliers", "forecast-runs",
     "users", "reports", "kpis", "recommendations", "notifications"],
)
def test_your_session_does_not_open_another_company(client: TestClient, module: str) -> None:  # noqa: F811
    headers_a, _company_a, _owner_a = _register(client, "ta", "20111111111")
    _headers_b, company_b, _owner_b = _register(client, "tb", "20111111112")
    res = client.get(f"{API}/companies/{company_b}/{module}", headers=headers_a)
    assert res.status_code == 403, res.text
