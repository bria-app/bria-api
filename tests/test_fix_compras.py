# ruff: noqa: F811  (pytest fixtures imported from test_audit_fixes are re-bound as arguments)
"""Regression tests for the purchases / suppliers fixes ("compras").

1. A purchase cannot be dated after today in Lima (single, batch and import rows).
2. Purchase documents and lines flag a deleted supplier (supplier_deleted) so the web
   stops linking to a supplier page that no longer exists.
3. Other write-path fixes: IGV-inclusive totals match the invoice, import batch ids only
   list documents that were saved, sale price / currency / size checks, supplier field lengths.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.modules.purchases.domain.dates import is_future, lima_today, occurred_at
from app.modules.suppliers.domain.ruc import ruc_check_digit
from tests.test_audit_fixes import API, _create_user, _register, client, db_factory  # noqa: F401

FUTURE_MSG = "La fecha de la compra no puede ser futura."


def _ruc(first_ten: str) -> str:
    return first_ten + str(ruc_check_digit(first_ten))


def _setup(client: TestClient) -> dict[str, Any]:
    owner, company_id, _ = _register(client, "c", "20123456786")
    base = f"{API}/companies/{company_id}"
    supplier = client.post(
        f"{base}/suppliers", headers=owner, json={"ruc": _ruc("2060000001"), "business_name": "Distribuidora Sol"}
    )
    assert supplier.status_code == 201, supplier.text
    product = client.post(f"{base}/products", headers=owner, json={"name": "Arroz 5kg", "unit_price": "25"})
    assert product.status_code == 201, product.text
    return {"h": owner, "base": base, "supplier_id": supplier.json()["id"], "product_id": product.json()["id"]}


def _stock(client: TestClient, ctx: dict[str, Any]) -> int:
    catalog = client.get(f"{ctx['base']}/purchases/catalog", headers=ctx["h"]).json()
    return next(p["stock_on_hand"] for p in catalog if p["id"] == ctx["product_id"])


def _tomorrow() -> str:
    return (lima_today() + timedelta(days=1)).isoformat()


# --- 1. future dates ----------------------------------------------------------------------
class TestFutureDate:
    def test_lima_today_and_noon_placement(self) -> None:
        # 03:00 UTC on the 5th is still the 4th in Lima (UTC-5).
        late_night = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)
        assert lima_today(late_night) == date(2026, 11, 4)
        assert not is_future(date(2026, 11, 4), late_night)
        assert is_future(date(2026, 11, 5), late_night)
        # A purchase dated "today" in Lima happens now, even when UTC is already tomorrow.
        assert occurred_at(date(2026, 11, 4), late_night) == late_night
        # Back-dated: noon in Lima = 17:00 UTC.
        assert occurred_at(date(2026, 11, 1), late_night) == datetime(2026, 11, 1, 17, 0, tzinfo=timezone.utc)

    def test_single_purchase_rejects_future_date(self, client: TestClient) -> None:
        ctx = _setup(client)
        body = {
            "supplier_id": ctx["supplier_id"],
            "product_id": ctx["product_id"],
            "purchase_date": _tomorrow(),
            "quantity": 5,
            "unit_cost": "10",
        }
        res = client.post(f"{ctx['base']}/purchases", headers=ctx["h"], json=body)
        assert res.status_code == 422, res.text
        assert res.json()["message"] == FUTURE_MSG
        assert _stock(client, ctx) == 0

        body["purchase_date"] = lima_today().isoformat()
        assert client.post(f"{ctx['base']}/purchases", headers=ctx["h"], json=body).status_code == 201
        assert _stock(client, ctx) == 5

    def test_batch_rejects_future_date(self, client: TestClient) -> None:
        ctx = _setup(client)
        body = {
            "supplier_id": ctx["supplier_id"],
            "purchase_date": _tomorrow(),
            "items": [{"product_id": ctx["product_id"], "quantity": 3, "unit_cost": "8"}],
        }
        res = client.post(f"{ctx['base']}/purchases/batch", headers=ctx["h"], json=body)
        assert res.status_code == 422, res.text
        assert res.json()["message"] == FUTURE_MSG
        assert _stock(client, ctx) == 0

    def test_import_marks_only_future_rows(self, client: TestClient) -> None:
        ctx = _setup(client)
        yesterday = (lima_today() - timedelta(days=1)).isoformat()
        body = {
            "supplier_id": ctx["supplier_id"],
            "purchase_date": lima_today().isoformat(),
            "rows": [
                {"row": 2, "name": "Arroz 5kg", "quantity": 2, "unit_cost": "10"},
                {"row": 3, "name": "Arroz 5kg", "quantity": 7, "unit_cost": "10", "purchase_date": _tomorrow()},
                {"row": 4, "name": "Arroz 5kg", "quantity": 1, "unit_cost": "10", "purchase_date": yesterday},
            ],
        }
        res = client.post(f"{ctx['base']}/purchases/import", headers=ctx["h"], json=body)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["created_lines"] == 2
        assert data["errors"] == [{"row": 3, "message": FUTURE_MSG}]
        assert _stock(client, ctx) == 3

    def test_import_with_future_header_date_fails_rows_without_own_date(self, client: TestClient) -> None:
        ctx = _setup(client)
        body = {
            "supplier_id": ctx["supplier_id"],
            "purchase_date": _tomorrow(),
            "rows": [
                {"row": 2, "name": "Arroz 5kg", "quantity": 2, "unit_cost": "10"},
                {"row": 3, "name": "Arroz 5kg", "quantity": 4, "unit_cost": "10", "purchase_date": lima_today().isoformat()},
            ],
        }
        data = client.post(f"{ctx['base']}/purchases/import", headers=ctx["h"], json=body).json()
        assert data["created_lines"] == 1
        assert [e["row"] for e in data["errors"]] == [2]
        assert _stock(client, ctx) == 4


# --- 2. deleted supplier flag ------------------------------------------------------------
class TestDeletedSupplierFlag:
    def test_documents_and_lines_flag_deleted_supplier(self, client: TestClient) -> None:
        ctx = _setup(client)
        body = {
            "supplier_id": ctx["supplier_id"],
            "purchase_date": lima_today().isoformat(),
            "document_number": "F001-123",
            "items": [{"product_id": ctx["product_id"], "quantity": 3, "unit_cost": "8"}],
        }
        batch = client.post(f"{ctx['base']}/purchases/batch", headers=ctx["h"], json=body).json()
        doc_url = f"{ctx['base']}/purchases/documents/{batch['batch_id']}"

        page = client.get(f"{ctx['base']}/purchases/documents", headers=ctx["h"]).json()
        assert page["items"][0]["supplier_deleted"] is False
        detail = client.get(doc_url, headers=ctx["h"]).json()
        assert detail["supplier_deleted"] is False
        assert detail["lines"][0]["supplier_deleted"] is False
        lines = client.get(f"{ctx['base']}/purchases", headers=ctx["h"]).json()
        assert lines[0]["supplier_deleted"] is False

        assert client.delete(f"{ctx['base']}/suppliers/{ctx['supplier_id']}", headers=ctx["h"]).status_code == 200

        page = client.get(f"{ctx['base']}/purchases/documents", headers=ctx["h"]).json()
        item = page["items"][0]
        assert item["supplier_deleted"] is True
        assert item["supplier_id"] == ctx["supplier_id"]
        assert item["supplier_name"] == "Proveedor eliminado"
        detail = client.get(doc_url, headers=ctx["h"]).json()
        assert detail["supplier_deleted"] is True
        assert detail["supplier_id"] == ctx["supplier_id"]
        assert all(line["supplier_deleted"] for line in detail["lines"])
        lines = client.get(f"{ctx['base']}/purchases", headers=ctx["h"]).json()
        assert lines[0]["supplier_deleted"] is True


# --- 3. other write-path fixes ------------------------------------------------------------
class TestWritePaths:
    def test_igv_inclusive_totals_match_invoice(self, client: TestClient) -> None:
        ctx = _setup(client)
        body = {
            "supplier_id": ctx["supplier_id"],
            "purchase_date": lima_today().isoformat(),
            "costs_include_igv": True,
            "items": [{"product_id": ctx["product_id"], "quantity": 1000, "unit_cost": "10.00"}],
        }
        data = client.post(f"{ctx['base']}/purchases/batch", headers=ctx["h"], json=body).json()
        # Invoice: 1000 x S/ 10.00 with IGV = S/ 10 000.00 (before: 9 994.60).
        assert Decimal(data["total"]) == Decimal("10000.00")
        assert Decimal(data["subtotal"]) == Decimal("8474.58")
        assert Decimal(data["lines"][0]["unit_cost"]) == Decimal("8.47")

    def test_net_costs_unchanged(self, client: TestClient) -> None:
        ctx = _setup(client)
        body = {
            "supplier_id": ctx["supplier_id"],
            "purchase_date": lima_today().isoformat(),
            "items": [{"product_id": ctx["product_id"], "quantity": 3, "unit_cost": "8.50"}],
        }
        data = client.post(f"{ctx['base']}/purchases/batch", headers=ctx["h"], json=body).json()
        assert Decimal(data["subtotal"]) == Decimal("25.50")
        assert Decimal(data["igv"]) == Decimal("4.59")
        assert Decimal(data["total"]) == Decimal("30.09")

    def test_import_batch_ids_skip_documents_that_failed(self, client: TestClient) -> None:
        ctx = _setup(client)
        body = {
            "supplier_id": ctx["supplier_id"],
            "purchase_date": lima_today().isoformat(),
            "rows": [
                {"row": 2, "name": "Arroz 5kg", "quantity": 2, "unit_cost": "10", "document_number": "F001-1"},
                {"row": 3, "name": "Arroz 5kg", "quantity": 0, "unit_cost": "10", "document_number": "F001-2"},
            ],
        }
        data = client.post(f"{ctx['base']}/purchases/import", headers=ctx["h"], json=body).json()
        assert data["created_lines"] == 1
        assert len(data["batch_ids"]) == 1
        assert data["batch_id"] == data["batch_ids"][0]
        res = client.get(f"{ctx['base']}/purchases/documents/{data['batch_ids'][0]}", headers=ctx["h"])
        assert res.status_code == 200

    def test_new_product_negative_price_rejected(self, client: TestClient) -> None:
        ctx = _setup(client)
        body = {
            "supplier_id": ctx["supplier_id"],
            "purchase_date": lima_today().isoformat(),
            "items": [{"new_product": {"name": "Fideos", "unit_price": "-5"}, "quantity": 1, "unit_cost": "2"}],
        }
        res = client.post(f"{ctx['base']}/purchases/batch", headers=ctx["h"], json=body)
        assert res.status_code == 422
        assert "precio de venta no puede ser negativo" in res.json()["message"]

    def test_huge_quantity_and_foreign_currency_rejected(self, client: TestClient) -> None:
        ctx = _setup(client)
        body = {
            "supplier_id": ctx["supplier_id"],
            "product_id": ctx["product_id"],
            "purchase_date": lima_today().isoformat(),
            "quantity": 5_000_000_000,
            "unit_cost": "1",
        }
        res = client.post(f"{ctx['base']}/purchases", headers=ctx["h"], json=body)
        assert res.status_code == 422
        assert "demasiado grande" in res.json()["message"]

        body.update(quantity=1, currency="USD")
        res = client.post(f"{ctx['base']}/purchases", headers=ctx["h"], json=body)
        assert res.status_code == 422
        assert "soles" in res.json()["message"]
        body["currency"] = "pen"
        assert client.post(f"{ctx['base']}/purchases", headers=ctx["h"], json=body).json()["currency"] == "PEN"

    def test_supplier_field_lengths(self, client: TestClient) -> None:
        ctx = _setup(client)
        res = client.post(
            f"{ctx['base']}/suppliers",
            headers=ctx["h"],
            json={"ruc": _ruc("2060000002"), "business_name": "Otro", "phone": "9" * 31},
        )
        assert res.status_code == 422
        assert res.json()["message"] == "El teléfono es muy largo (máximo 30 caracteres)."
        res = client.patch(
            f"{ctx['base']}/suppliers/{ctx['supplier_id']}", headers=ctx["h"], json={"address": "x" * 501}
        )
        assert res.status_code == 422
        assert "dirección" in res.json()["message"]
        ok = client.patch(f"{ctx['base']}/suppliers/{ctx['supplier_id']}", headers=ctx["h"], json={"phone": "999888777"})
        assert ok.status_code == 200 and ok.json()["phone"] == "999888777"

    def test_viewer_cannot_register_purchases(self, client: TestClient) -> None:
        ctx = _setup(client)
        company_id = ctx["base"].rsplit("/", 1)[-1]
        user_id, viewer = _create_user(client, ctx["h"], company_id, "mirador", "admin")
        client.patch(f"{API}/companies/{company_id}/users/{user_id}/role", headers=ctx["h"], json={"role": "viewer"})
        body = {
            "supplier_id": ctx["supplier_id"],
            "purchase_date": lima_today().isoformat(),
            "items": [{"product_id": ctx["product_id"], "quantity": 1, "unit_cost": "1"}],
        }
        assert client.post(f"{ctx['base']}/purchases/batch", headers=viewer, json=body).status_code == 403
        assert _stock(client, ctx) == 0
