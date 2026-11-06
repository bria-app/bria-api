# ruff: noqa: F811  (pytest fixtures imported from test_audit_fixes are re-bound as arguments)
"""Catalog fixes: sellers never see costs, products/categories with history are not
hard-deleted, and imported custom attributes are typed by their field definition."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.custom_fields.domain.values import coerce_value
from app.shared.domain.errors import ValidationError
from tests.test_audit_fixes import API, _create_user, _register, client, db_factory  # noqa: F401

TAX_ID = "20123456786"


def _setup(client: TestClient) -> tuple[dict[str, str], str]:
    headers, company_id, _ = _register(client, "cat", TAX_ID)
    return headers, f"{API}/companies/{company_id}"


def _product(client: TestClient, headers: dict[str, str], base: str, **extra: Any) -> dict[str, Any]:
    body = {"name": extra.pop("name", "Collar"), "unit_cost": "12.50", "unit_price": "20.00", **extra}
    res = client.post(f"{base}/products", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


# --- 1. Sellers never see costs ------------------------------------------------------
class TestSellerCosts:
    def test_seller_reads_products_without_costs(self, client: TestClient) -> None:
        headers, base = _setup(client)
        product = _product(client, headers, base, initial_stock=3)
        _, seller = _create_user(client, headers, base.rsplit("/", 1)[1], "cajero1", "seller")

        listed = client.get(f"{base}/products", headers=seller)
        assert listed.status_code == 200
        row = listed.json()[0]
        assert "unit_cost" in row and row["unit_cost"] is None
        assert "last_cost" in row and row["last_cost"] is None
        assert Decimal(row["unit_price"]) == Decimal("20.00")

        one = client.get(f"{base}/products/{product['id']}", headers=seller).json()
        assert one["unit_cost"] is None and one["last_cost"] is None

    def test_seller_timeline_hides_costs_and_margin(self, client: TestClient) -> None:
        headers, base = _setup(client)
        product = _product(client, headers, base, initial_stock=5)
        _, seller = _create_user(client, headers, base.rsplit("/", 1)[1], "cajero2", "seller")

        owner_view = client.get(f"{base}/products/{product['id']}/timeline", headers=headers).json()
        assert owner_view["product"]["unit_cost"] is not None
        assert any(e["unit_cost"] is not None for e in owner_view["events"])

        res = client.get(f"{base}/products/{product['id']}/timeline", headers=seller)
        assert res.status_code == 200
        data = res.json()
        assert data["product"]["unit_cost"] is None
        assert data["product"]["last_cost"] is None
        assert data["stats"]["gross_margin_pct"] is None
        assert data["events"], "the initial stock movement is still listed"
        assert all(e["unit_cost"] is None for e in data["events"])
        assert data["stats"]["stock_on_hand"] == 5

    def test_owner_and_analyst_still_see_costs(self, client: TestClient) -> None:
        headers, base = _setup(client)
        _product(client, headers, base)
        company_id = base.rsplit("/", 1)[1]
        user_id, analyst = _create_user(client, headers, company_id, "analista1", "admin")
        assert client.patch(
            f"{base}/users/{user_id}/role", headers=headers, json={"role": "analyst"}
        ).status_code == 200
        for who in (headers, analyst):
            row = client.get(f"{base}/products", headers=who).json()[0]
            assert Decimal(row["unit_cost"]) == Decimal("12.50")


# --- 2. Products with history are not deleted ---------------------------------------
class TestDeleteProduct:
    def test_clean_product_is_deleted(self, client: TestClient) -> None:
        headers, base = _setup(client)
        product = _product(client, headers, base)
        assert client.delete(f"{base}/products/{product['id']}", headers=headers).status_code == 200
        assert client.get(f"{base}/products/{product['id']}", headers=headers).status_code == 404

    def test_product_with_stock_movement_is_kept(self, client: TestClient) -> None:
        headers, base = _setup(client)
        product = _product(client, headers, base, initial_stock=2)
        res = client.delete(f"{base}/products/{product['id']}", headers=headers)
        assert res.status_code == 409
        assert "ponlo en pausa" in res.text
        assert client.get(f"{base}/products/{product['id']}", headers=headers).status_code == 200

    @pytest.mark.parametrize("kind", ["sale", "purchase", "recommendation", "forecast", "lost_sale"])
    def test_product_with_history_is_kept(
        self, client: TestClient, db_factory: sessionmaker[Session], kind: str  # noqa: F811
    ) -> None:
        from uuid import uuid4

        from app.modules.forecasting.infrastructure.persistence.models import ForecastResultModel
        from app.modules.purchases.infrastructure.persistence.models import PurchaseModel
        from app.modules.recommendations.infrastructure.persistence.models import RecommendationModel
        from app.modules.sales.infrastructure.persistence.models import LostSaleModel, SaleModel

        headers, base = _setup(client)
        product = _product(client, headers, base)
        company_id, product_id = UUID(base.rsplit("/", 1)[1]), UUID(product["id"])
        rows = {
            "sale": lambda: SaleModel(
                company_id=company_id, product_id=product_id, sale_date=date.today(), quantity=1,
                unit_price=Decimal("20"), total_amount=Decimal("20"),
            ),
            "purchase": lambda: PurchaseModel(
                company_id=company_id, supplier_id=uuid4(), product_id=product_id,
                purchase_date=date.today(), quantity=1, unit_cost=Decimal("10"), total_amount=Decimal("10"),
            ),
            "recommendation": lambda: RecommendationModel(
                company_id=company_id, product_id=product_id, recommended_quantity=4, priority="high",
            ),
            "forecast": lambda: ForecastResultModel(
                run_id=uuid4(), company_id=company_id, product_id=product_id, points=[],
            ),
            "lost_sale": lambda: _lost_sale(LostSaleModel, company_id, product_id),
        }
        with db_factory() as db:
            db.add(rows[kind]())
            db.commit()

        res = client.delete(f"{base}/products/{product['id']}", headers=headers)
        assert res.status_code == 409, res.text
        assert client.get(f"{base}/products/{product['id']}", headers=headers).status_code == 200


def _lost_sale(model: Any, company_id: UUID, product_id: UUID) -> Any:
    from datetime import datetime, timezone

    return model(
        company_id=company_id, product_id=product_id, requested_quantity=2, available_quantity=0,
        occurred_at=datetime.now(timezone.utc),
    )


# --- 3. Categories with children are not deleted ------------------------------------
class TestDeleteCategory:
    def _category(self, client: TestClient, headers: dict[str, str], base: str, **body: Any) -> str:
        res = client.post(f"{base}/product-categories", headers=headers, json={"name": "Perros", **body})
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def test_empty_category_is_deleted(self, client: TestClient) -> None:
        headers, base = _setup(client)
        cat = self._category(client, headers, base)
        assert client.delete(f"{base}/product-categories/{cat}", headers=headers).status_code == 200

    def test_category_with_subcategory_is_kept(self, client: TestClient) -> None:
        headers, base = _setup(client)
        parent = self._category(client, headers, base)
        self._category(client, headers, base, name="Collares", parent_id=parent)
        res = client.delete(f"{base}/product-categories/{parent}", headers=headers)
        assert res.status_code == 409
        assert "subcategoría" in res.json()["message"]
        assert client.get(f"{base}/product-categories/{parent}", headers=headers).status_code == 200

    def test_category_with_paused_product_is_kept(self, client: TestClient) -> None:
        headers, base = _setup(client)
        cat = self._category(client, headers, base)
        product = _product(client, headers, base, category_id=cat)
        assert client.patch(
            f"{base}/products/{product['id']}", headers=headers, json={"is_active": False}
        ).status_code == 200
        res = client.delete(f"{base}/product-categories/{cat}", headers=headers)
        assert res.status_code == 409
        assert "pausados" in res.text
        # Once the product moves out, the category can go.
        assert client.patch(
            f"{base}/products/{product['id']}", headers=headers, json={"category_id": None}
        ).status_code == 200
        assert client.delete(f"{base}/product-categories/{cat}", headers=headers).status_code == 200


# --- 4. Import casts custom attributes ----------------------------------------------
class TestImportCustomAttributes:
    def _field(self, client: TestClient, headers: dict[str, str], base: str, label: str, field_type: str,
               options: list[str] | None = None) -> str:
        res = client.post(
            f"{base}/custom-fields", headers=headers,
            json={"entity": "product", "label": label, "field_type": field_type, "options": options or []},
        )
        assert res.status_code == 201, res.text
        return res.json()["key"]

    def test_values_are_typed(self, client: TestClient) -> None:
        headers, base = _setup(client)
        peso = self._field(client, headers, base, "Peso", "number")
        precio = self._field(client, headers, base, "Precio mayorista", "currency")
        importado = self._field(client, headers, base, "Importado", "boolean")
        vence = self._field(client, headers, base, "Vence", "date")
        talla = self._field(client, headers, base, "Talla", "select", ["S", "M", "L"])
        rows = [
            {"row": 2, "name": "Collar S", "unit_price": "10",
             "custom_attributes": {peso: "1,5", precio: "S/ 1,250.50", importado: "Sí", vence: "31/12/2026",
                                   talla: "m", "nota_libre": "texto"}},
            {"row": 3, "name": "Collar M", "unit_price": "10",
             "custom_attributes": {peso: "2", importado: "x", vence: "2026-01-05"}},
            {"row": 4, "name": "Collar L", "unit_price": "10", "custom_attributes": {importado: "no"}},
        ]
        res = client.post(f"{base}/products/import", headers=headers, json={"rows": rows})
        assert res.status_code == 200, res.text
        assert res.json()["created"] == 3 and res.json()["errors"] == []

        by_name = {p["name"]: p["custom_attributes"] for p in client.get(f"{base}/products", headers=headers).json()}
        assert by_name["Collar S"] == {
            peso: 1.5, precio: 1250.5, importado: True, vence: "2026-12-31", talla: "M", "nota_libre": "texto",
        }
        assert by_name["Collar M"] == {peso: 2, importado: True, vence: "2026-01-05"}
        assert by_name["Collar L"] == {importado: False}

    def test_bad_values_are_row_errors(self, client: TestClient) -> None:
        headers, base = _setup(client)
        peso = self._field(client, headers, base, "Peso", "number")
        talla = self._field(client, headers, base, "Talla", "select", ["S", "M", "L"])
        importado = self._field(client, headers, base, "Importado", "boolean")
        vence = self._field(client, headers, base, "Vence", "date")
        rows = [
            {"row": 2, "name": "Bueno", "unit_price": "10", "custom_attributes": {peso: "3"}},
            {"row": 3, "name": "Malo1", "unit_price": "10", "custom_attributes": {peso: "tres"}},
            {"row": 4, "name": "Malo2", "unit_price": "10", "custom_attributes": {talla: "XXL"}},
            {"row": 5, "name": "Malo3", "unit_price": "10", "custom_attributes": {importado: "quizás"}},
            {"row": 6, "name": "Malo4", "unit_price": "10", "custom_attributes": {vence: "31/02/2026"}},
        ]
        res = client.post(f"{base}/products/import", headers=headers, json={"rows": rows})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["created"] == 1
        errors = {e["row"]: e["message"] for e in body["errors"]}
        assert set(errors) == {3, 4, 5, 6}
        assert errors[3].startswith("Peso:")
        assert "opciones" in errors[4] and "S, M, L" in errors[4]
        assert "Sí o No" in errors[5]
        assert "fecha" in errors[6]
        names = {p["name"] for p in client.get(f"{base}/products", headers=headers).json()}
        assert names == {"Bueno"}


@pytest.mark.parametrize(
    ("field_type", "raw", "expected"),
    [
        ("number", "12,5", 12.5),
        ("number", "1.250,75", 1250.75),
        ("number", "12,500,000", 12500000),
        ("number", 7, 7),
        ("currency", "S/. 10", 10),
        ("currency", "3.456", 3.46),
        ("boolean", "SI", True),
        ("boolean", "1", True),
        ("boolean", "false", False),
        ("boolean", "0", False),
        ("date", "2026-03-04T10:00:00", "2026-03-04"),
        ("date", "04-03-2026", "2026-03-04"),
        ("text", " libre ", " libre "),
    ],
)
def test_coerce_value(field_type: str, raw: Any, expected: Any) -> None:
    assert coerce_value(field_type, raw, label="Campo") == expected


def test_coerce_value_rejects_bool_as_number() -> None:
    with pytest.raises(ValidationError):
        coerce_value("number", True, label="Peso")
