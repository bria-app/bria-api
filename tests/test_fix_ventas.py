# ruff: noqa: F811  (pytest fixtures imported from test_audit_fixes are re-bound as arguments)
"""Regression tests for the sales/inventory fixes (key «ventas»).

1. Voiding a ticket only returns the stock it really took out (imported history never did).
2. GET /sales-orders/lookup never returns an inactive product.
3. GET /sales carries product_name and sku.
4. GET /inventory/movements filters by reference_type and keeps paging.
5. Sellers never receive cost or margin fields from inventory and sales-order reads.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient

import app.main  # noqa: F401  (registers every table before the in-memory database is created)
from tests.test_audit_fixes import API, _create_user, _register, client, db_factory  # noqa: F401

RUC = "20123456786"


def _base(company_id: str) -> str:
    return f"{API}/companies/{company_id}"


def _product(
    client: TestClient, headers: dict[str, str], company_id: str, sku: str, *, stock: int = 10,
    cost: str = "4.00", price: str = "10.00", barcode: str | None = None,
) -> dict[str, Any]:
    res = client.post(
        f"{_base(company_id)}/products",
        headers=headers,
        json={"sku": sku, "name": f"Producto {sku}", "unit_cost": cost, "unit_price": price,
              "initial_stock": stock, "barcode": barcode},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _stock(client: TestClient, headers: dict[str, str], company_id: str, product_id: str) -> int:
    res = client.get(f"{_base(company_id)}/inventory/current-stock/{product_id}", headers=headers)
    assert res.status_code == 200, res.text
    return int(res.json()["quantity_on_hand"])


def _sell(client: TestClient, headers: dict[str, str], company_id: str, product_id: str, qty: int) -> dict[str, Any]:
    res = client.post(
        f"{_base(company_id)}/sales-orders",
        headers=headers,
        json={"items": [{"product_id": product_id, "quantity": qty, "unit_price": "10.00"}],
              "document_type": "nota_venta"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _import(client: TestClient, headers: dict[str, str], company_id: str, sku: str, qty: int, *, affect_stock: bool) -> None:
    res = client.post(
        f"{_base(company_id)}/sales/import",
        headers=headers,
        json={"rows": [{"row": 1, "code": sku, "sale_date": (date.today() - timedelta(days=1)).isoformat(),
                        "quantity": qty, "unit_price": "10"}],
              "affect_stock": affect_stock},
    )
    assert res.status_code == 201, res.text
    assert res.json()["created"] == 1, res.text


def _orders(client: TestClient, headers: dict[str, str], company_id: str) -> list[dict[str, Any]]:
    res = client.get(f"{_base(company_id)}/sales-orders", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["items"]


def _void(client: TestClient, headers: dict[str, str], company_id: str, order_id: str) -> None:
    res = client.post(f"{_base(company_id)}/sales-orders/{order_id}/void", headers=headers, json={"reason": "prueba"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "voided"


# --- 1. void only returns stock that moved ---------------------------------------
class TestVoidReturnsOnlyMovedStock:
    def test_voiding_imported_history_does_not_add_stock(self, client: TestClient) -> None:
        headers, cid, _ = _register(client, "v1", RUC)
        p = _product(client, headers, cid, "H-1", stock=10)
        _import(client, headers, cid, "H-1", 3, affect_stock=False)
        assert _stock(client, headers, cid, p["id"]) == 10
        (order,) = _orders(client, headers, cid)
        _void(client, headers, cid, order["id"])
        assert _stock(client, headers, cid, p["id"]) == 10
        voids = client.get(f"{_base(cid)}/inventory/movements?reference_type=sale_void", headers=headers).json()
        assert voids == []

    def test_voiding_bulk_sale_returns_its_units(self, client: TestClient) -> None:
        headers, cid, _ = _register(client, "v2", RUC)
        p = _product(client, headers, cid, "B-1", stock=10)
        _import(client, headers, cid, "B-1", 4, affect_stock=True)
        assert _stock(client, headers, cid, p["id"]) == 6
        (order,) = _orders(client, headers, cid)
        _void(client, headers, cid, order["id"])
        assert _stock(client, headers, cid, p["id"]) == 10

    def test_voiding_till_ticket_returns_its_units(self, client: TestClient) -> None:
        headers, cid, _ = _register(client, "v3", RUC)
        p = _product(client, headers, cid, "T-1", stock=10)
        order = _sell(client, headers, cid, p["id"], 3)
        assert _stock(client, headers, cid, p["id"]) == 7
        _void(client, headers, cid, order["id"])
        assert _stock(client, headers, cid, p["id"]) == 10
        voids = client.get(f"{_base(cid)}/inventory/movements?reference_type=sale_void", headers=headers).json()
        assert [(m["product_id"], m["quantity"], m["movement_type"]) for m in voids] == [(p["id"], 3, "inbound")]


# --- 2. lookup skips inactive products ------------------------------------------------
def test_lookup_ignores_inactive_products(client: TestClient) -> None:
    headers, cid, _ = _register(client, "l1", RUC)
    p = _product(client, headers, cid, "L-1", barcode="7750000000017")
    ok = client.get(f"{_base(cid)}/sales-orders/lookup", headers=headers, params={"code": "7750000000017"})
    assert ok.status_code == 200 and ok.json()["id"] == p["id"]
    off = client.patch(f"{_base(cid)}/products/{p['id']}", headers=headers, json={"is_active": False})
    assert off.status_code == 200, off.text
    for code in ("7750000000017", "l-1"):
        res = client.get(f"{_base(cid)}/sales-orders/lookup", headers=headers, params={"code": code})
        assert res.status_code == 404, res.text


# --- 3. imported history carries product labels -----------------------------------------
def test_imported_sales_carry_product_name_and_sku(client: TestClient) -> None:
    headers, cid, _ = _register(client, "s1", RUC)
    _product(client, headers, cid, "N-1", stock=10)
    _import(client, headers, cid, "N-1", 2, affect_stock=False)
    res = client.get(f"{_base(cid)}/sales", headers=headers, params={"origin": "imported"})
    assert res.status_code == 200, res.text
    (sale,) = res.json()
    assert sale["product_name"] == "Producto N-1"
    assert sale["sku"] == "N-1"
    one = client.get(f"{_base(cid)}/sales/{sale['id']}", headers=headers).json()
    assert one["product_name"] == "Producto N-1" and one["sku"] == "N-1"


# --- 4. movements filter and paging ---------------------------------------------------------
def test_movements_filter_by_reference_type_and_page(client: TestClient) -> None:
    headers, cid, _ = _register(client, "m1", RUC)
    p = _product(client, headers, cid, "M-1", stock=20)
    for _ in range(3):
        _sell(client, headers, cid, p["id"], 1)
    url = f"{_base(cid)}/inventory/movements"
    all_moves = client.get(url, headers=headers).json()
    assert {m["reference_type"] for m in all_moves} == {"initial", "sale"}
    sales = client.get(url, headers=headers, params={"reference_type": "sale"}).json()
    assert len(sales) == 3 and all(m["reference_type"] == "sale" for m in sales)
    page1 = client.get(url, headers=headers, params={"reference_type": "sale", "size": 2, "page": 1}).json()
    page2 = client.get(url, headers=headers, params={"reference_type": "sale", "size": 2, "page": 2}).json()
    assert len(page1) == 2 and len(page2) == 1
    assert {m["id"] for m in page1 + page2} == {m["id"] for m in sales}
    assert client.get(url, headers=headers, params={"reference_type": "nada"}).json() == []


# --- 5. sellers never see costs ------------------------------------------------------------------
class TestSellerSeesNoCosts:
    def _setup(self, client: TestClient) -> tuple[dict[str, str], dict[str, str], str, dict[str, Any]]:
        headers, cid, _ = _register(client, "c1", RUC)
        _, seller = _create_user(client, headers, cid, "cajero1", "seller")
        p = _product(client, headers, cid, "C-1", stock=10)
        return headers, seller, cid, p

    def test_sales_orders_hide_costs_for_seller(self, client: TestClient) -> None:
        headers, seller, cid, p = self._setup(client)
        created = _sell(client, seller, cid, p["id"], 2)
        assert created["cost_total"] is None and created["gross_margin"] is None
        assert all(line["unit_cost"] is None for line in created["lines"])

        detail = client.get(f"{_base(cid)}/sales-orders/{created['id']}", headers=seller).json()
        assert detail["cost_total"] is None and detail["gross_margin"] is None
        assert all(line["unit_cost"] is None for line in detail["lines"])
        row = _orders(client, seller, cid)[0]
        assert row["cost_total"] is None and row["margin"] is None
        summary = client.get(f"{_base(cid)}/sales-orders/summary", headers=seller).json()
        assert summary["cost_total"] is None and summary["gross_margin"] is None and summary["margin_pct"] is None
        assert summary["revenue"] == "20.00"
        sales = client.get(f"{_base(cid)}/sales", headers=seller).json()
        assert sales and all(s["unit_cost"] is None for s in sales)
        lookup = client.get(f"{_base(cid)}/sales-orders/lookup", headers=seller, params={"code": "C-1"}).json()
        assert "unit_cost" not in lookup

        # The owner still sees everything.
        owner = client.get(f"{_base(cid)}/sales-orders/{created['id']}", headers=headers).json()
        assert owner["cost_total"] == "8.00" and owner["lines"][0]["unit_cost"] is not None
        assert _orders(client, headers, cid)[0]["margin"] is not None
        assert client.get(f"{_base(cid)}/sales-orders/summary", headers=headers).json()["cost_total"] == "8.00"

    def test_inventory_hides_costs_for_seller(self, client: TestClient) -> None:
        headers, seller, cid, p = self._setup(client)
        overview = client.get(f"{_base(cid)}/inventory/overview", headers=seller)
        assert overview.status_code == 200, overview.text
        body = overview.json()
        item = body["items"][0]
        assert item["unit_cost"] is None and item["last_cost"] is None and item["stock_value"] is None
        assert item["stock_on_hand"] == 10 and item["unit_price"] == "10.00"
        assert body["totals"]["inventory_value_cost"] is None and body["totals"]["potential_margin"] is None

        valuation = client.get(f"{_base(cid)}/inventory/valuation", headers=seller).json()
        assert valuation["totals"]["inventory_value_cost"] is None
        assert all(g["value_cost"] is None and g["share_pct"] is None for g in valuation["by_category"] + valuation["by_brand"])

        moves = client.get(f"{_base(cid)}/inventory/movements", headers=seller).json()
        assert moves and all(m["unit_cost"] is None for m in moves)
        one = client.get(f"{_base(cid)}/inventory/movements/{moves[0]['id']}", headers=seller).json()
        assert one["unit_cost"] is None

        owner = client.get(f"{_base(cid)}/inventory/overview", headers=headers).json()
        assert owner["items"][0]["unit_cost"] == "4.00" and owner["items"][0]["stock_value"] == "40.00"
        assert owner["totals"]["potential_margin"] == "60.00"
        owner_val = client.get(f"{_base(cid)}/inventory/valuation", headers=headers).json()
        assert owner_val["by_category"][0]["share_pct"] == 100.0
