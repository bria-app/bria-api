"""Tenant isolation (audit A-01, M-11, C-02): company A must never reach company B's data.

Two companies are registered and company B gets one record of every entity that has an
id-based route. Each route is then called with company A's token, company A's
``company_id`` in the path and **B's entity id**; the answer must be 404 (or 403) — or,
for the few "list by product" read models, an empty result — and B's record must be
intact afterwards.

``test_every_id_route_is_covered`` walks ``app.routes`` so a new id-based route that is
not listed here (and is neither a scaffold nor a global route) fails the suite.
"""
from __future__ import annotations

import inspect
import re
from collections.abc import Generator
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

API = "/api/v1"


@dataclass
class Tenant:
    company_id: str
    headers: dict[str, str]
    ids: dict[str, str]


@dataclass(frozen=True)
class Case:
    method: str
    path: str  # relative to /companies/{company_id}; {name} is replaced by B's id
    body: dict[str, Any] | None = None
    expect: str = "not_found"  # "not_found" (403/404) | "empty" (200 + nothing of B)
    check: str | None = None  # GET path (B's token) proving B's record is intact


_TODAY = date.today().isoformat()

CASES: list[Case] = [
    # companies / users (C-02)
    Case("PATCH", "/users/{user_id}", {"full_name": "Hacked"}),
    Case("PATCH", "/users/{user_id}/role", {"role": "admin"}),
    Case("DELETE", "/users/{user_id}"),
    # products / categories
    Case("GET", "/products/{product_id}"),
    Case("PATCH", "/products/{product_id}", {"name": "Hacked"}, check="/products/{product_id}"),
    Case("DELETE", "/products/{product_id}", check="/products/{product_id}"),
    Case("GET", "/products/{product_id}/timeline"),
    Case("GET", "/product-categories/{category_id}"),
    Case("PATCH", "/product-categories/{category_id}", {"name": "Hacked"}, check="/product-categories/{category_id}"),
    Case("DELETE", "/product-categories/{category_id}", check="/product-categories/{category_id}"),
    # sales
    Case("GET", f"/sales/by-product/{{product_id}}?start=2000-01-01&end={_TODAY}", expect="empty"),
    Case("GET", "/sales/{sale_id}"),
    Case("DELETE", "/sales/{sale_id}", check="/sales/{sale_id}"),
    Case("GET", "/sales/batches/{batch_id}"),
    Case("GET", "/sales-orders/{order_id}"),
    Case("POST", "/sales-orders/{order_id}/void", {"reason": "x"}, check="/sales-orders/{order_id}"),
    # invoicing
    Case("GET", "/invoices/{invoice_id}"),
    Case("POST", "/invoices/{invoice_id}/void", check="/invoices/{invoice_id}"),
    # custom fields
    Case("PATCH", "/custom-fields/{field_id}", {"label": "Hacked"}),
    Case("DELETE", "/custom-fields/{field_id}"),
    # inventory
    Case("GET", "/inventory/current-stock/{product_id}"),
    Case("GET", "/inventory/movements/{movement_id}"),
    Case("GET", "/inventory/snapshots/by-product/{product_id}", expect="empty"),
    Case("PATCH", "/inventory/replenishments/{replenishment_id}", {"status": "cancelled"}),
    Case("PATCH", "/inventory/stockouts/{stockout_id}", {}),
    # ingestion / data preparation
    Case("GET", "/ingestion/uploads/{upload_id}"),
    Case("POST", "/ingestion/uploads/{upload_id}/mapping", {"mapping": {"a": "b"}}, check="/ingestion/uploads/{upload_id}"),
    Case("POST", "/ingestion/uploads/{upload_id}/validate", check="/ingestion/uploads/{upload_id}"),
    Case("GET", "/data-preparation/datasets/{dataset_id}"),
    Case("DELETE", "/data-preparation/datasets/{dataset_id}", check="/data-preparation/datasets/{dataset_id}"),
    # forecasting
    Case("GET", "/forecast-runs/{run_id}"),
    Case("GET", "/forecast-runs/{run_id}/status"),
    Case("GET", "/forecast-runs/{run_id}/results"),
    Case("GET", "/forecast-runs/{run_id}/metrics"),
    Case("GET", "/forecast-runs/{run_id}/tracking"),
    Case("GET", "/forecast-runs/{run_id}/overview"),
    Case("POST", "/forecast-runs/{run_id}/execute", check="/forecast-runs/{run_id}"),
    Case("POST", "/forecast-runs/{run_id}/cancel", check="/forecast-runs/{run_id}"),
    Case("GET", "/forecast-runs/by-product/{product_id}", expect="empty"),
    Case("GET", "/forecast-runs/product-insight/{product_id}"),
    # KPIs / recommendations
    Case("GET", "/kpis/by-product/{product_id}", expect="empty"),
    Case("GET", "/recommendations/{recommendation_id}"),
    Case("POST", "/recommendations/{recommendation_id}/accept", check="/recommendations/{recommendation_id}"),
    Case("POST", "/recommendations/{recommendation_id}/dismiss", check="/recommendations/{recommendation_id}"),
    # modules that already scoped by company (regression guard)
    Case("GET", "/suppliers/{supplier_id}"),
    Case("GET", "/suppliers/{supplier_id}/summary"),
    Case("PATCH", "/suppliers/{supplier_id}", {"business_name": "Hacked"}, check="/suppliers/{supplier_id}"),
    Case("DELETE", "/suppliers/{supplier_id}", check="/suppliers/{supplier_id}"),
    Case("GET", "/notifications/{notification_id}"),
    Case("DELETE", "/notifications/{notification_id}", check="/notifications/{notification_id}"),
    Case("POST", "/notifications/{notification_id}/mark-read", check="/notifications/{notification_id}"),
    Case("GET", "/files/{file_id}"),
    Case("GET", "/files/{file_id}/download"),
    Case("GET", "/files/{file_id}/metadata"),
    Case("DELETE", "/files/{file_id}", check="/files/{file_id}"),
    Case("PUT", "/dashboard/widgets/{widget_id}", {"title": "Hacked"}),
    Case("DELETE", "/dashboard/widgets/{widget_id}"),
    Case("GET", "/reports/{report_id}"),
    Case("GET", "/reports/{report_id}/download"),
    Case("POST", "/reports/{report_id}/regenerate"),
    Case("PATCH", "/validation/rules/{rule_id}", {"rule_name": "Hacked"}),
    Case("DELETE", "/validation/rules/{rule_id}"),
]

# Id routes that are intentionally not part of the matrix.
#  * global catalog routes (no tenant data) and the super-admin module;
#  * routes whose id is a free-form key of the caller's own company (preferences);
#  * purchase documents need a whole purchase flow; GetPurchaseDocument already filters
#    by company (checked in review) — kept out to keep the fixture small.
EXCLUDED = {
    "/api/v1/billing/plans/{plan_id}",
    "/api/v1/admin/system/settings/{key}",
    "/api/v1/companies/{company_id}/preferences/{key}",
    "/api/v1/companies/{company_id}/purchases/documents/{document_id}",
}

_SCAFFOLD_MARKERS = ("scaffold", "Placeholder", "Not implemented", "NotImplementedError")


def _is_scaffold(route: APIRoute) -> bool:
    try:
        source = inspect.getsource(route.endpoint)
    except (OSError, TypeError):
        return False
    return any(marker in source for marker in _SCAFFOLD_MARKERS)


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    from app.main import app
    from app.modules.companies.infrastructure.persistence import models  # noqa: F401
    from app.shared.infrastructure.database import Base, get_db

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)  # no lifespan: no real database is touched
    test_client.app_state = {"session_factory": testing_session}  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def _register(client: TestClient, suffix: str, tax_id: str) -> Tenant:
    res = client.post(
        f"{API}/auth/register",
        json={
            "email": f"owner{suffix}@tienda.pe",
            "password": "secret123",
            "full_name": f"Owner {suffix}",
            "company_name": f"Tienda {suffix}",
            "tax_id": tax_id,
        },
    )
    assert res.status_code == 201, res.text
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    company_id = client.get(f"{API}/auth/me", headers=headers).json()["company_id"]
    return Tenant(company_id=company_id, headers=headers, ids={})


def _ok(res: Any) -> dict[str, Any]:
    assert res.status_code in (200, 201), res.text
    body: dict[str, Any] = res.json()
    return body


def _seed_company_b(client: TestClient, b: Tenant) -> None:
    base = f"{API}/companies/{b.company_id}"
    h = b.headers

    def post(path: str, json: dict[str, Any]) -> dict[str, Any]:
        return _ok(client.post(base + path, headers=h, json=json))

    b.ids["user_id"] = post(
        "/users",
        {"full_name": "Vendedora B", "username": "vendedorab", "password": "secret123", "role": "seller"},
    )["id"]
    b.ids["category_id"] = post("/product-categories", {"name": "Categoria B"})["id"]
    product = post(
        "/products",
        {"name": "SECRETO-B", "unit_price": "10", "unit_cost": "5", "initial_stock": 50},
    )
    b.ids["product_id"] = product["id"]
    pid = product["id"]
    b.ids["sale_id"] = post(
        "/sales", {"product_id": pid, "sale_date": _TODAY, "quantity": 1, "unit_price": "10"}
    )["id"]
    b.ids["batch_id"] = post("/sales/batches", {"source_file": "b.csv"})["id"]
    b.ids["order_id"] = post(
        "/sales-orders", {"items": [{"product_id": pid, "quantity": 1, "unit_price": "10"}]}
    )["id"]
    b.ids["invoice_id"] = post(
        "/invoices",
        {"document_type": "boleta", "items": [{"description": "x", "quantity": 1, "unit_price": "10"}]},
    )["id"]
    b.ids["field_id"] = post("/custom-fields", {"entity": "product", "label": "Color B"})["id"]
    b.ids["movement_id"] = post(
        "/inventory/movements", {"product_id": pid, "movement_type": "inbound", "quantity": 3}
    )["id"]
    post("/inventory/snapshots", {"product_id": pid, "quantity_on_hand": 7})
    b.ids["replenishment_id"] = post("/inventory/replenishments", {"product_id": pid, "quantity": 4})["id"]
    b.ids["stockout_id"] = post("/inventory/stockouts", {"product_id": pid})["id"]
    upload = client.post(
        base + "/ingestion/uploads",
        headers=h,
        files={"file": ("ventas.csv", b"date,sku,qty\n2026-01-01,A,1\n", "text/csv")},
    )
    b.ids["upload_id"] = _ok(upload)["id"]
    b.ids["dataset_id"] = post("/data-preparation/datasets", {"series": []})["id"]
    post("/kpis", {"product_id": pid, "kpi_type": "coverage_days", "value": "12"})
    b.ids["recommendation_id"] = post(
        "/recommendations", {"product_id": pid, "recommended_quantity": 5}
    )["id"]
    b.ids["supplier_id"] = post("/suppliers", {"ruc": "20999999990", "business_name": "Proveedor B"})["id"]
    b.ids["notification_id"] = post("/notifications", {"title": "Aviso B", "message": "SECRETO-B"})["id"]
    file_res = client.post(
        base + "/files",
        headers=h,
        files={"file": ("b.txt", b"SECRETO-B", "text/plain")},
    )
    b.ids["file_id"] = _ok(file_res)["id"]
    b.ids["widget_id"] = post("/dashboard/widgets", {"title": "Widget B", "widget_type": "chart"})["id"]
    b.ids["report_id"] = post("/reports", {"title": "Reporte B", "report_type": "kpi"})["id"]
    b.ids["rule_id"] = post("/validation/rules", {"rule_name": "Regla B", "rule_type": "format"})["id"]

    # A finished forecast run of B (inserted directly: the engine is not available here).
    from app.modules.forecasting.domain.entities import ForecastRun
    from app.modules.forecasting.infrastructure.persistence.repositories import (
        SqlForecastRunRepository,
    )

    factory = client.app_state["session_factory"]  # type: ignore[attr-defined]
    with factory() as session:
        run = SqlForecastRunRepository(session).add(
            ForecastRun(
                company_id=UUID(b.company_id),
                model_name="FTGM",
                horizon_days=30,
                dataset_id=UUID(b.ids["dataset_id"]),
            )
        )
        session.commit()
    assert run.id is not None
    b.ids["run_id"] = str(run.id)


@pytest.fixture(scope="module")
def tenants(client: TestClient) -> tuple[Tenant, Tenant]:
    a = _register(client, "a", "20111111111")
    b = _register(client, "b", "20222222222")
    _seed_company_b(client, b)
    return a, b


def _fill(path: str, ids: dict[str, str]) -> str:
    return re.sub(r"{(\w+)}", lambda m: ids[m.group(1)], path)


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.method} {c.path}")
def test_cross_tenant_id_is_rejected(
    client: TestClient, tenants: tuple[Tenant, Tenant], case: Case
) -> None:
    a, b = tenants
    url = f"{API}/companies/{a.company_id}{_fill(case.path, b.ids)}"
    res = client.request(case.method, url, headers=a.headers, json=case.body)

    if case.expect == "empty":
        assert res.status_code in (200, 403, 404), res.text
        if res.status_code == 200:
            assert res.json() in ([], {}), res.text
    else:
        assert res.status_code in (403, 404), f"{case.method} {url} -> {res.status_code} {res.text}"
    assert "SECRETO-B" not in res.text

    if case.check:
        intact = client.get(
            f"{API}/companies/{b.company_id}{_fill(case.check, b.ids)}", headers=b.headers
        )
        assert intact.status_code == 200, intact.text
        assert "Hacked" not in intact.text


def test_company_b_still_reads_its_own_records(
    client: TestClient, tenants: tuple[Tenant, Tenant]
) -> None:
    """Positive control: the ids used above are valid for their owner."""
    _, b = tenants
    for path in (
        "/products/{product_id}",
        "/sales/{sale_id}",
        "/invoices/{invoice_id}",
        "/forecast-runs/{run_id}",
        "/recommendations/{recommendation_id}",
        "/inventory/movements/{movement_id}",
        "/ingestion/uploads/{upload_id}",
        "/data-preparation/datasets/{dataset_id}",
        "/product-categories/{category_id}",
    ):
        res = client.get(f"{API}/companies/{b.company_id}{_fill(path, b.ids)}", headers=b.headers)
        assert res.status_code == 200, f"{path}: {res.text}"
    stock = client.get(
        f"{API}/companies/{b.company_id}/inventory/snapshots/by-product/{b.ids['product_id']}",
        headers=b.headers,
    )
    assert stock.status_code == 200 and len(stock.json()) == 1


def test_company_list_only_returns_own_company(
    client: TestClient, tenants: tuple[Tenant, Tenant]
) -> None:
    """C-03: GET /companies no longer enumerates every tenant; POST /companies is gone."""
    a, _ = tenants
    res = client.get(f"{API}/companies", headers=a.headers)
    assert res.status_code == 200, res.text
    assert [c["id"] for c in res.json()] == [a.company_id]
    created = client.post(
        f"{API}/companies",
        headers=a.headers,
        json={"name": "Otra", "tax_id": "20333333333", "email": "x@y.pe"},
    )
    assert created.status_code == 405


def _real_routes(routes: list, prefix: str = "") -> list[tuple[str, APIRoute]]:
    """Every APIRoute with its full path. `app.routes` only shows the included routers as wrappers
    (and /health), so walking it alone would find nothing and this guard would always pass."""
    out: list[tuple[str, APIRoute]] = []
    for route in routes:
        if isinstance(route, APIRoute):
            out.append((prefix + route.path, route))
            continue
        inner = next((getattr(route, a, None) for a in ("router", "original_router", "_router") if getattr(route, a, None)), None)
        if inner is not None and hasattr(inner, "routes"):
            out.extend(_real_routes(inner.routes, prefix + getattr(route, "prefix", "")))
    return out


def test_every_id_route_is_covered() -> None:
    """Every real (non-scaffold) tenant route with an entity id is in CASES or EXCLUDED."""
    from app.main import app

    covered = {
        (c.method, f"{API}/companies/{{company_id}}{c.path.split('?')[0]}") for c in CASES
    }
    # OpenAPI has the full paths; the routes have the code, to tell a scaffold from the real thing.
    paths = app.openapi()["paths"]
    routes = _real_routes(list(app.routes))
    assert len(routes) > 100, f"the route walker found only {len(routes)} routes"

    def endpoint_for(method: str, path: str) -> APIRoute | None:
        found = [r for full, r in routes if method in r.methods and path.endswith(full)]
        return max(found, key=lambda r: len(r.path), default=None)

    missing = []
    for path, operations in paths.items():
        ids = [p for p in re.findall(r"{(\w+)}", path) if p != "company_id"]
        if not ids or path in EXCLUDED or "{company_id}" not in path:
            continue  # global routes (no tenant in the path) are listed in EXCLUDED
        for operation in operations:
            method = operation.upper()
            if (method, path) in covered:
                continue
            route = endpoint_for(method, path)
            if route is None or not _is_scaffold(route):
                missing.append(f"{method} {path}")
    assert not missing, f"id routes without a cross-tenant test: {missing}"
