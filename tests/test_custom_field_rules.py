# ruff: noqa: F811  (pytest fixtures imported from test_audit_fixes are re-bound as arguments)
"""Advanced rules of own columns: validation by type and one alert per column.

Rules are validated themselves (422 in Spanish), product values are checked on create,
update and import (per-row errors), existing data keeps working, and product reads
carry the alerts the columns raise.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  (registers every ORM model before the fixture creates the schema)
from app.modules.custom_fields.domain.rules import (
    check_value,
    evaluate_alert,
    lima_today,
    normalize_rules,
    public_rules,
)
from app.shared.domain.errors import ValidationError
from tests.test_audit_fixes import API, _create_user, _register, client, db_factory  # noqa: F401

TAX_ID = "20123456786"
TODAY = date(2026, 11, 5)


# --- domain: normalize_rules -----------------------------------------------------------
class TestNormalizeRules:
    def test_empty_and_public_shape(self) -> None:
        assert normalize_rules("text", None, label="Código") == {}
        assert normalize_rules("text", {"validation": {}, "alert": None}, label="Código") == {}
        assert public_rules({}) == {"validation": {}, "alert": None}

    def test_text_rules_are_kept_and_idempotent(self) -> None:
        raw = {"validation": {"max_length": "8", "only": "digits"}}
        rules = normalize_rules("text", raw, label="Código")
        assert rules == {"validation": {"max_length": 8, "only": "digits"}}
        assert normalize_rules("text", rules, label="Código") == rules
        assert normalize_rules("text", public_rules(rules), label="Código") == rules

    def test_off_values_are_dropped(self) -> None:
        rules = normalize_rules(
            "number", {"validation": {"integer_only": False, "min": None, "max": 10}}, label="Cajas"
        )
        assert rules == {"validation": {"max": 10}}

    @pytest.mark.parametrize(
        ("field_type", "raw", "fragment"),
        [
            ("date", {"validation": {"max_length": 5}}, "no aplica a una columna de tipo Fecha"),
            ("text", {"validation": {"only": "emoji"}}, "Elige qué admite"),
            ("text", {"validation": {"max_length": 0}}, "entre 1 y 1000"),
            ("number", {"validation": {"min": 10, "max": 1}}, "mínimo no puede ser mayor"),
            ("number", {"validation": {"min": "diez"}}, "mínimo debe ser un número"),
            ("number", {"validation": {"integer_only": True, "decimals": 2}}, "no ambos"),
            ("number", {"validation": {"integer_only": True, "min": 0.5}}, "número entero"),
            ("currency", {"validation": {"decimals": 3}}, "2 decimales"),
            ("date", {"validation": {"date_limit": "manana"}}, "futura o no puede ser pasada"),
            ("text", {"validation": {"color": "rojo"}}, "desconocida"),
            ("text", {"otra": {}}, "Regla desconocida"),
            ("text", "x", "deben ser un objeto"),
            ("date", {"alert": {"op": "lt", "value": 3}}, "no aplica a una columna de tipo Fecha"),
            ("number", {"alert": {"op": "lt"}}, "valor numérico"),
            ("number", {"alert": {"op": "nope"}}, "Elige una condición"),
            ("date", {"alert": {"op": "within_days", "days": 0}}, "cuántos días"),
            ("select", {"alert": {"op": "eq", "value": "XL"}}, "no está entre las opciones"),
            ("boolean", {"alert": {"op": "eq", "value": "tal vez"}}, "Sí o No"),
            ("text", {"alert": {"op": "eq", "value": " "}}, "Escribe el texto"),
            ("url", {"alert": {"op": "eq", "value": "x"}}, "no aplica"),
            ("number", {"alert": {"op": "lt", "value": 1, "tone": "red"}}, "tono"),
            ("number", {"alert": {"op": "lt", "value": 1, "label": "x" * 41}}, "40 caracteres"),
            ("number", {"alert": {"op": "lt", "value": 1, "color": "x"}}, "desconocido"),
        ],
    )
    def test_wrong_combinations_are_rejected(self, field_type: str, raw: Any, fragment: str) -> None:
        with pytest.raises(ValidationError) as exc:
            normalize_rules(field_type, raw, label="Columna", options=["S", "M", "L"])
        assert fragment in exc.value.message

    def test_alert_defaults(self) -> None:
        within = normalize_rules("date", {"alert": {"op": "within_days", "days": 30}}, label="Vencimiento")
        assert within["alert"] == {
            "op": "within_days", "days": 30, "include_past": True, "label": "Por vencer", "tone": "warning",
        }
        empty = normalize_rules("text", {"alert": {"op": "empty", "tone": "danger"}}, label="Marca")
        assert empty["alert"] == {"op": "empty", "label": "Sin marca", "tone": "danger"}
        select = normalize_rules("select", {"alert": {"op": "eq", "value": "m"}}, label="Talla", options=["S", "M"])
        assert select["alert"]["value"] == "M"
        boolean = normalize_rules("boolean", {"alert": {"op": "eq", "value": "Sí"}}, label="Frágil")
        assert boolean["alert"]["value"] is True

    def test_alert_only_for_products(self) -> None:
        with pytest.raises(ValidationError, match="productos"):
            normalize_rules("text", {"alert": {"op": "empty"}}, label="Banco", entity="supplier")


# --- domain: check_value ------------------------------------------------------------------
class TestCheckValue:
    @pytest.mark.parametrize(
        ("field_type", "validation", "value", "fragment"),
        [
            ("text", {"max_length": 3}, "ABCD", "Columna: admite hasta 3 caracteres (tiene 4)."),
            ("text", {"only": "digits"}, "12A", "solo admite dígitos (0-9)"),
            ("text", {"only": "letters"}, "Rojo2", "solo admite letras"),
            ("text", {"only": "letters_numbers"}, "AB-12", "solo admite letras y números"),
            ("text", {"only": "email"}, "ana@", "no es un correo válido"),
            ("number", {"integer_only": True}, 2.5, "debe ser un número entero"),
            ("number", {"decimals": 1}, 2.25, "admite hasta 1 decimales"),
            ("number", {"decimals": 0}, 2.5, "no admite decimales"),
            ("number", {"min": 0}, -1, "debe ser 0 o más"),
            ("currency", {"max": 100}, 150.5, "debe ser S/ 100 o menos (S/ 150.5)"),
            ("date", {"date_limit": "not_future"}, "2026-11-06", "no puede ser una fecha futura (06/11/2026)"),
            ("date", {"date_limit": "not_past"}, "2026-11-04", "no puede ser una fecha pasada"),
        ],
    )
    def test_breaking_values(self, field_type: str, validation: dict[str, Any], value: Any, fragment: str) -> None:
        with pytest.raises(ValidationError) as exc:
            check_value(field_type, {"validation": validation}, value, label="Columna", today=TODAY)
        assert fragment in exc.value.message

    @pytest.mark.parametrize(
        ("field_type", "validation", "value"),
        [
            ("text", {"only": "digits", "max_length": 8}, "12345678"),
            ("text", {"only": "digits"}, 12345.0),
            ("text", {"only": "letters"}, "Azul marino ñandú"),
            ("text", {"only": "letters_numbers"}, "Lote 12B"),
            ("text", {"only": "email"}, "ana@tienda.pe"),
            ("number", {"integer_only": True, "min": 0, "max": 10}, 10),
            ("number", {"decimals": 2}, 2.25),
            ("date", {"date_limit": "not_future"}, "2026-11-05"),
            ("date", {"date_limit": "not_past"}, "2026-11-05"),
            ("text", {"max_length": 1}, ""),
            ("number", {"min": 5}, None),
        ],
    )
    def test_fitting_values(self, field_type: str, validation: dict[str, Any], value: Any) -> None:
        check_value(field_type, {"validation": validation}, value, label="Columna", today=TODAY)

    def test_no_rules_never_raise(self) -> None:
        check_value("text", {}, "lo que sea", label="X", today=TODAY)
        check_value("number", None, "abc", label="X", today=TODAY)


# --- domain: evaluate_alert ----------------------------------------------------------------
def _alert(field_type: str, alert: dict[str, Any], options: list[str] | None = None) -> dict[str, Any]:
    return normalize_rules(field_type, {"alert": alert}, label="Columna", options=options)


class TestEvaluateAlert:
    @pytest.mark.parametrize(
        ("op", "limit", "value", "fires"),
        [
            ("lt", 5, 4, True), ("lt", 5, 5, False), ("lte", 5, 5, True), ("gt", 5, 6, True),
            ("gt", 5, 5, False), ("gte", 5, 5, True), ("eq", 5, 5.0, True), ("eq", 5, 4, False),
            ("lt", 5, "3", True), ("lt", 5, None, False), ("lt", 5, "abc", False),
        ],
    )
    def test_numbers(self, op: str, limit: int, value: Any, fires: bool) -> None:
        rules = _alert("number", {"op": op, "value": limit, "label": "Bajo", "tone": "danger"})
        hit = evaluate_alert("number", rules, value, today=TODAY)
        assert (hit is not None) is fires
        if fires:
            assert hit == {"label": "Bajo", "tone": "danger"}

    def test_dates(self) -> None:
        soon = _alert("date", {"op": "within_days", "days": 30})
        only_future = _alert("date", {"op": "within_days", "days": 30, "include_past": False})
        past = _alert("date", {"op": "past", "label": "Vencido", "tone": "danger"})
        in_10 = (TODAY + timedelta(days=10)).isoformat()
        in_31 = (TODAY + timedelta(days=31)).isoformat()
        yesterday = (TODAY - timedelta(days=1)).isoformat()
        assert evaluate_alert("date", soon, in_10, today=TODAY) == {"label": "Por vencer", "tone": "warning"}
        assert evaluate_alert("date", soon, TODAY.isoformat(), today=TODAY) is not None
        assert evaluate_alert("date", soon, in_31, today=TODAY) is None
        assert evaluate_alert("date", soon, yesterday, today=TODAY) is not None
        assert evaluate_alert("date", only_future, yesterday, today=TODAY) is None
        assert evaluate_alert("date", past, yesterday, today=TODAY) == {"label": "Vencido", "tone": "danger"}
        assert evaluate_alert("date", past, TODAY.isoformat(), today=TODAY) is None
        assert evaluate_alert("date", past, "04/11/2026", today=TODAY) is not None  # old stored format

    def test_select_boolean_text_and_empty(self) -> None:
        select = _alert("select", {"op": "eq", "value": "Agotado"}, options=["Activo", "Agotado"])
        assert evaluate_alert("select", select, "agotado", today=TODAY) is not None
        assert evaluate_alert("select", select, "Activo", today=TODAY) is None
        boolean = _alert("boolean", {"op": "eq", "value": False})
        assert evaluate_alert("boolean", boolean, False, today=TODAY) is not None
        assert evaluate_alert("boolean", boolean, True, today=TODAY) is None
        assert evaluate_alert("boolean", boolean, None, today=TODAY) is None
        text = _alert("text", {"op": "eq", "value": "Revisar"})
        assert evaluate_alert("text", text, " revisar ", today=TODAY) is not None
        empty = _alert("text", {"op": "empty"})
        assert evaluate_alert("text", empty, None, today=TODAY) is not None
        assert evaluate_alert("text", empty, "  ", today=TODAY) is not None
        assert evaluate_alert("text", empty, "Nike", today=TODAY) is None

    def test_malformed_rules_never_raise(self) -> None:
        assert evaluate_alert("number", {"alert": {"op": "lt", "value": "x"}}, 1, today=TODAY) is None
        assert evaluate_alert("number", {"alert": "nope"}, 1, today=TODAY) is None
        assert evaluate_alert("date", {"alert": {"op": "within_days", "days": "x"}}, "2026-11-06", today=TODAY) is None
        assert evaluate_alert("number", None, 1, today=TODAY) is None


# --- API -----------------------------------------------------------------------------------
def _setup(client: TestClient) -> tuple[dict[str, str], str]:
    headers, company_id, _ = _register(client, "rules", TAX_ID)
    return headers, f"{API}/companies/{company_id}"


def _field(client: TestClient, headers: dict[str, str], base: str, label: str, field_type: str,
           rules: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    body = {"entity": "product", "label": label, "field_type": field_type, **extra}
    if rules is not None:
        body["rules"] = rules
    res = client.post(f"{base}/custom-fields", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _product(client: TestClient, headers: dict[str, str], base: str, attrs: dict[str, Any], **extra: Any) -> Any:
    body = {"name": extra.pop("name", "Collar"), "unit_cost": "5", "unit_price": "10",
            "custom_attributes": attrs, **extra}
    return client.post(f"{base}/products", headers=headers, json=body)


class TestRulesApi:
    def test_rules_round_trip_and_default(self, client: TestClient) -> None:
        headers, base = _setup(client)
        plain = _field(client, headers, base, "Marca", "text")
        assert plain["rules"] == {"validation": {}, "alert": None}
        code = _field(client, headers, base, "Código interno", "text",
                      rules={"validation": {"only": "digits", "max_length": 6}})
        assert code["rules"] == {"validation": {"only": "digits", "max_length": 6}, "alert": None}
        listed = {f["key"]: f for f in client.get(f"{base}/custom-fields?entity=product", headers=headers).json()}
        assert listed[code["key"]]["rules"]["validation"]["only"] == "digits"
        assert listed[plain["key"]]["rules"] == {"validation": {}, "alert": None}

        patched = client.patch(f"{base}/custom-fields/{code['id']}", headers=headers,
                               json={"rules": {"alert": {"op": "empty"}}})
        assert patched.status_code == 200, patched.text
        assert patched.json()["rules"] == {
            "validation": {}, "alert": {"op": "empty", "label": "Sin código interno", "tone": "warning"},
        }
        kept = client.patch(f"{base}/custom-fields/{code['id']}", headers=headers, json={"is_required": True})
        assert kept.json()["rules"]["alert"]["op"] == "empty"
        cleared = client.patch(f"{base}/custom-fields/{code['id']}", headers=headers, json={"rules": {}})
        assert cleared.json()["rules"] == {"validation": {}, "alert": None}

    def test_bad_rules_are_422_in_spanish(self, client: TestClient) -> None:
        headers, base = _setup(client)
        res = client.post(f"{base}/custom-fields", headers=headers, json={
            "entity": "product", "label": "Vence", "field_type": "date",
            "rules": {"validation": {"max_length": 4}},
        })
        assert res.status_code == 422
        assert res.json()["message"] == "«Máximo de caracteres» no aplica a una columna de tipo Fecha."
        talla = _field(client, headers, base, "Talla", "select", options=["S", "M"],
                       rules={"alert": {"op": "eq", "value": "M", "label": "Talla M"}})
        res = client.patch(f"{base}/custom-fields/{talla['id']}", headers=headers, json={"options": ["S", "L"]})
        assert res.status_code == 422
        assert "«M», que no está entre las opciones" in res.json()["message"]

    def test_values_are_validated_on_create_and_update(self, client: TestClient) -> None:
        headers, base = _setup(client)
        code = _field(client, headers, base, "Código interno", "text",
                      rules={"validation": {"only": "digits"}})["key"]
        cajas = _field(client, headers, base, "Cajas", "number",
                       rules={"validation": {"integer_only": True, "min": 1}})["key"]

        bad = _product(client, headers, base, {code: "A1"})
        assert bad.status_code == 422
        assert bad.json()["message"] == "Código interno: «A1» no es válido, solo admite dígitos (0-9)."
        bad = _product(client, headers, base, {cajas: "0"})
        assert bad.status_code == 422 and bad.json()["message"].startswith("Cajas: debe ser 1 o más")
        bad = _product(client, headers, base, {cajas: "dos"})
        assert bad.status_code == 422 and bad.json()["message"].startswith("Cajas:")

        good = _product(client, headers, base, {code: "00123", cajas: "3"})
        assert good.status_code == 201, good.text
        product = good.json()
        assert product["custom_attributes"] == {code: "00123", cajas: 3}
        assert product["alerts"] == []

        url = f"{base}/products/{product['id']}"
        res = client.patch(url, headers=headers, json={"custom_attributes": {code: "00123", cajas: 2.5}})
        assert res.status_code == 422 and "número entero" in res.json()["message"]
        res = client.patch(url, headers=headers, json={"custom_attributes": {code: "00999", cajas: 4}})
        assert res.status_code == 200, res.text

    def test_existing_values_keep_working_after_a_rule_is_added(self, client: TestClient) -> None:
        headers, base = _setup(client)
        field = _field(client, headers, base, "Lote", "text")
        product = _product(client, headers, base, {field["key"]: "AB-1"}).json()
        client.patch(f"{base}/custom-fields/{field['id']}", headers=headers,
                     json={"rules": {"validation": {"only": "digits"}}})
        url = f"{base}/products/{product['id']}"
        # Editing another attribute or field keeps the old value untouched.
        res = client.patch(url, headers=headers, json={"name": "Collar rojo", "custom_attributes": {field["key"]: "AB-1"}})
        assert res.status_code == 200, res.text
        assert res.json()["custom_attributes"] == {field["key"]: "AB-1"}
        res = client.patch(url, headers=headers, json={"custom_attributes": {field["key"]: "AB-2"}})
        assert res.status_code == 422

    def test_import_reports_rule_errors_per_row(self, client: TestClient) -> None:
        headers, base = _setup(client)
        dni = _field(client, headers, base, "DNI proveedor", "text",
                     rules={"validation": {"only": "digits", "max_length": 8}})["key"]
        compra = _field(client, headers, base, "Fecha de compra", "date",
                        rules={"validation": {"date_limit": "not_future"}})["key"]
        future = (lima_today() + timedelta(days=3)).strftime("%d/%m/%Y")
        rows = [
            {"row": 2, "name": "Bueno", "unit_price": "10", "custom_attributes": {dni: "12345678", compra: "01/01/2026"}},
            {"row": 3, "name": "Largo", "unit_price": "10", "custom_attributes": {dni: "123456789"}},
            {"row": 4, "name": "Futuro", "unit_price": "10", "custom_attributes": {compra: future}},
            {"row": 5, "name": "Numero", "unit_price": "10", "custom_attributes": {dni: 87654321}},
        ]
        res = client.post(f"{base}/products/import", headers=headers, json={"rows": rows})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["created"] == 2
        errors = {e["row"]: e["message"] for e in body["errors"]}
        assert set(errors) == {3, 4}
        assert errors[3] == "DNI proveedor: admite hasta 8 caracteres (tiene 9)."
        assert errors[4].startswith("Fecha de compra: no puede ser una fecha futura")


class TestAlertsApi:
    def test_products_carry_alerts(self, client: TestClient) -> None:
        headers, base = _setup(client)
        vence = _field(client, headers, base, "Vencimiento", "date",
                       rules={"alert": {"op": "within_days", "days": 30, "tone": "danger"}})["key"]
        marca = _field(client, headers, base, "Marca", "text", rules={"alert": {"op": "empty"}})["key"]
        soon = (lima_today() + timedelta(days=5)).isoformat()
        later = (lima_today() + timedelta(days=90)).isoformat()
        a = _product(client, headers, base, {vence: soon}, name="Leche").json()
        b = _product(client, headers, base, {vence: later, marca: "Gloria"}, name="Queso").json()

        assert a["alerts"] == [
            {"key": vence, "column": "Vencimiento", "label": "Por vencer", "tone": "danger"},
            {"key": marca, "column": "Marca", "label": "Sin marca", "tone": "warning"},
        ]
        assert b["alerts"] == []
        listed = {p["name"]: p["alerts"] for p in client.get(f"{base}/products", headers=headers).json()}
        assert [x["label"] for x in listed["Leche"]] == ["Por vencer", "Sin marca"]
        assert listed["Queso"] == []
        one = client.get(f"{base}/products/{a['id']}", headers=headers).json()
        assert len(one["alerts"]) == 2
        timeline = client.get(f"{base}/products/{a['id']}/timeline", headers=headers).json()
        assert len(timeline["product"]["alerts"]) == 2

        res = client.patch(f"{base}/products/{a['id']}", headers=headers,
                           json={"custom_attributes": {vence: later, marca: "Gloria"}})
        assert res.json()["alerts"] == []

    def test_seller_sees_alerts_without_costs(self, client: TestClient) -> None:
        headers, base = _setup(client)
        stock = _field(client, headers, base, "Cajas", "number",
                       rules={"alert": {"op": "lt", "value": 2, "label": "Pocas cajas"}})["key"]
        _product(client, headers, base, {stock: 1})
        _, seller = _create_user(client, headers, base.rsplit("/", 1)[1], "cajero9", "seller")
        row = client.get(f"{base}/products", headers=seller).json()[0]
        assert row["unit_cost"] is None and row["last_cost"] is None
        assert row["alerts"] == [{"key": stock, "column": "Cajas", "label": "Pocas cajas", "tone": "warning"}]

    def test_scoped_column_only_alerts_its_categories(self, client: TestClient) -> None:
        headers, base = _setup(client)
        food = client.post(f"{base}/product-categories", headers=headers, json={"name": "Alimentos"}).json()
        dairy = client.post(f"{base}/product-categories", headers=headers,
                            json={"name": "Lácteos", "parent_id": food["id"]}).json()
        toys = client.post(f"{base}/product-categories", headers=headers, json={"name": "Juguetes"}).json()
        vence = _field(client, headers, base, "Vencimiento", "date", category_ids=[food["id"]],
                       rules={"alert": {"op": "empty", "label": "Falta vencimiento"}})["key"]
        assert vence
        _product(client, headers, base, {}, name="Yogurt", category_id=dairy["id"])
        _product(client, headers, base, {}, name="Pelota", category_id=toys["id"])
        _product(client, headers, base, {}, name="Suelto")
        listed = {p["name"]: p["alerts"] for p in client.get(f"{base}/products", headers=headers).json()}
        assert [x["label"] for x in listed["Yogurt"]] == ["Falta vencimiento"]
        assert listed["Pelota"] == [] and listed["Suelto"] == []
