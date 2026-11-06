"""Fixes «avisos-pronostico»: plain-words forecast notices, real notification paging,
unread count + mark all read, KPI message, idempotent accept, backtest filter on the runs
list and created_at on reports.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.forecasting.application.use_cases.execution import (
    low_stock_message,
    restock_message,
)
from app.modules.forecasting.infrastructure.background import _emit_notifications
from app.modules.forecasting.infrastructure.persistence.models import ForecastRunModel
from app.modules.notifications.infrastructure.persistence.models import NotificationModel
from app.modules.recommendations.infrastructure.persistence.models import (
    RecommendationModel,
)
from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.enums import ReportType
from app.modules.reports.infrastructure.persistence.repositories import SqlReportRepository
from tests.test_audit_fixes import API, _create_user, _register, client, db_factory  # noqa: F401

RUC_A = "20123456786"
RUC_B = "20600000005"
JARGON = ("recomendaciones de reabastecimiento", "sección Recomendaciones", "stock crítico",
          "stock de seguridad", "producto(s)", "FTGM")


# --- 1. forecast notices in plain words -------------------------------------------
class TestForecastNoticeCopy:
    def test_restock_singular_and_plural(self) -> None:
        assert restock_message(1) == (
            "Te sugerimos comprar 1 producto", "Míralo en Pronóstico, en «Qué comprar»."
        )
        title, text = restock_message(4)
        assert title == "Te sugerimos comprar 4 productos"
        assert text == "Míralos en Pronóstico, en «Qué comprar»."

    def test_low_stock_singular_and_plural(self) -> None:
        assert low_stock_message(1)[0] == "1 producto por acabarse"
        assert "Revísalo en Inventario" in low_stock_message(1)[1]
        assert low_stock_message(3)[0] == "3 productos por acabarse"
        assert "Revísalos en Inventario" in low_stock_message(3)[1]

    @pytest.mark.parametrize("n", [1, 2, 7])
    def test_no_jargon(self, n: int) -> None:
        for text in (*restock_message(n), *low_stock_message(n)):
            assert not any(word in text for word in JARGON), text

    def test_emitted_notices_use_new_copy(
        self, client: TestClient, db_factory: sessionmaker[Session]  # noqa: F811
    ) -> None:
        headers, company_id, _ = _register(client, "n1", RUC_A)
        # Two products at/below their minimum, one well stocked.
        for name, safety, stock in (("Arroz", 5, 2), ("Azúcar", 3, 0), ("Aceite", 2, 40)):
            res = client.post(
                f"{API}/companies/{company_id}/products",
                headers=headers,
                json={"name": name, "unit_price": "5.00", "safety_stock": safety,
                      "initial_stock": stock},
            )
            assert res.status_code == 201, res.text

        db = db_factory()
        try:
            _emit_notifications(db, UUID(company_id), 1, {"models": {"ftgm": 3}})
            db.commit()
            titles = {
                n.title: n.message
                for n in db.execute(
                    select(NotificationModel).where(
                        NotificationModel.company_id == UUID(company_id)
                    )
                ).scalars()
            }
        finally:
            db.close()
        assert titles["Te sugerimos comprar 1 producto"] == "Míralo en Pronóstico, en «Qué comprar»."
        assert "2 productos por acabarse" in titles
        for title, message in titles.items():
            if title.startswith("Pronóstico"):
                continue  # completion text keeps naming the model that won (audit M-01)
            assert not any(word in f"{title} {message}" for word in JARGON)


# --- 2. notifications: real total/pages, unread count, mark all read ---------------
def _notify(client: TestClient, headers: dict[str, str], company_id: str, n: int) -> list[str]:  # noqa: F811
    ids = []
    for i in range(n):
        res = client.post(
            f"{API}/companies/{company_id}/notifications",
            headers=headers,
            json={"title": f"Aviso {i}", "message": "Hola"},
        )
        assert res.status_code == 201, res.text
        ids.append(res.json()["id"])
    return ids


class TestNotifications:
    def test_list_reports_real_total_and_pages(self, client: TestClient) -> None:  # noqa: F811
        headers, company_id, _ = _register(client, "n2", RUC_A)
        _notify(client, headers, company_id, 5)
        url = f"{API}/companies/{company_id}/notifications"

        page1 = client.get(f"{url}?size=2", headers=headers).json()
        assert (page1["total"], page1["pages"], len(page1["items"])) == (5, 3, 2)
        page3 = client.get(f"{url}?size=2&page=3", headers=headers).json()
        assert (page3["total"], page3["pages"], len(page3["items"])) == (5, 3, 1)

        empty = client.get(f"{url}?unread_only=true&size=2", headers=headers).json()
        assert empty["total"] == 5
        client.post(f"{url}/mark-all-read", headers=headers)
        none_left = client.get(f"{url}?unread_only=true", headers=headers).json()
        assert (none_left["total"], none_left["pages"], none_left["items"]) == (0, 1, [])

    def test_unread_count_and_mark_all_read_stay_in_company(
        self, client: TestClient  # noqa: F811
    ) -> None:
        headers_a, company_a, _ = _register(client, "n3", RUC_A)
        headers_b, company_b, _ = _register(client, "n4", RUC_B)
        ids = _notify(client, headers_a, company_a, 3)
        _notify(client, headers_b, company_b, 2)
        url_a = f"{API}/companies/{company_a}/notifications"
        url_b = f"{API}/companies/{company_b}/notifications"

        assert client.get(f"{url_a}/unread-count", headers=headers_a).json() == {"unread": 3}
        client.post(f"{url_a}/{ids[0]}/mark-read", headers=headers_a)
        assert client.get(f"{url_a}/unread-count", headers=headers_a).json() == {"unread": 2}

        res = client.post(f"{url_a}/mark-all-read", headers=headers_a)
        assert res.status_code == 200, res.text
        assert res.json() == {"message": "Marcamos 2 avisos como leídos.", "updated": 2}
        assert client.get(f"{url_a}/unread-count", headers=headers_a).json() == {"unread": 0}
        # Idempotent, and the other company is untouched.
        again = client.post(f"{url_a}/mark-all-read", headers=headers_a).json()
        assert again["updated"] == 0
        assert client.get(f"{url_b}/unread-count", headers=headers_b).json() == {"unread": 2}

        # Another company's token cannot use these routes.
        assert client.post(f"{url_b}/mark-all-read", headers=headers_a).status_code == 403
        assert client.get(f"{url_b}/unread-count", headers=headers_a).status_code == 403

    def test_viewer_can_mark_all_read(self, client: TestClient) -> None:  # noqa: F811
        headers, company_id, _ = _register(client, "n5", RUC_A)
        _notify(client, headers, company_id, 1)
        user_id, viewer = _create_user(client, headers, company_id, "lector1", "admin")
        res = client.patch(
            f"{API}/companies/{company_id}/users/{user_id}/role", headers=headers,
            json={"role": "viewer"},
        )
        assert res.status_code == 200, res.text
        url = f"{API}/companies/{company_id}/notifications"
        assert client.get(f"{url}/unread-count", headers=viewer).json() == {"unread": 1}
        res = client.post(f"{url}/mark-all-read", headers=viewer)
        assert res.status_code == 200, res.text
        assert res.json()["message"] == "Marcamos 1 aviso como leído."


# --- 3. KPI message -----------------------------------------------------------------
def test_kpis_without_forecast_say_what_to_do(client: TestClient) -> None:  # noqa: F811
    headers, company_id, _ = _register(client, "k1", RUC_A)
    res = client.post(f"{API}/companies/{company_id}/kpis/calculate", headers=headers)
    assert res.status_code == 422, res.text
    assert res.json()["message"] == "Primero calcula un pronóstico en Pronóstico."
    assert "FTGM" not in res.text


# --- 4. accept is idempotent ----------------------------------------------------------
class TestAcceptRecommendation:
    def _rec(self, client: TestClient, headers: dict[str, str], company_id: str) -> str:  # noqa: F811
        res = client.post(
            f"{API}/companies/{company_id}/recommendations",
            headers=headers,
            json={"product_id": str(uuid4()), "recommended_quantity": 10, "priority": "high"},
        )
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def test_accept_twice_returns_it_unchanged(self, client: TestClient) -> None:  # noqa: F811
        headers, company_id, _ = _register(client, "r1", RUC_A)
        rec_id = self._rec(client, headers, company_id)
        url = f"{API}/companies/{company_id}/recommendations/{rec_id}/accept"
        first = client.post(url, headers=headers)
        assert first.status_code == 200, first.text
        second = client.post(url, headers=headers)
        assert second.status_code == 200, second.text
        assert second.json() == first.json()
        assert second.json()["status"] == "accepted"

    def test_dismissed_refuses_with_conflict(self, client: TestClient) -> None:  # noqa: F811
        headers, company_id, _ = _register(client, "r2", RUC_A)
        rec_id = self._rec(client, headers, company_id)
        base = f"{API}/companies/{company_id}/recommendations/{rec_id}"
        assert client.post(f"{base}/dismiss", headers=headers).status_code == 200
        res = client.post(f"{base}/accept", headers=headers)
        assert res.status_code == 409, res.text
        assert "descartada" in res.json()["message"]

    def test_superseded_refuses_with_conflict(
        self, client: TestClient, db_factory: sessionmaker[Session]  # noqa: F811
    ) -> None:
        headers, company_id, _ = _register(client, "r3", RUC_A)
        rec_id = self._rec(client, headers, company_id)
        db = db_factory()
        try:
            db.get(RecommendationModel, UUID(rec_id)).status = "superseded"
            db.commit()
        finally:
            db.close()
        res = client.post(
            f"{API}/companies/{company_id}/recommendations/{rec_id}/accept", headers=headers
        )
        assert res.status_code == 409, res.text
        assert "ya no está vigente" in res.json()["message"]


# --- 5. backtest filter on the runs list ------------------------------------------
def test_forecast_runs_filter_by_backtest(
    client: TestClient, db_factory: sessionmaker[Session]  # noqa: F811
) -> None:
    headers, company_id, _ = _register(client, "f1", RUC_A)
    db = db_factory()
    try:
        for backtest in (True, False, False):
            meta = {"backtest": backtest} if backtest else {}
            db.add(ForecastRunModel(
                company_id=UUID(company_id), model_name="FTGM", horizon_days=30,
                status="success", scope={"type": "all", "_meta": meta},
            ))
        db.add(ForecastRunModel(  # legacy run without scope: not a backtest
            company_id=UUID(company_id), model_name="FTGM", horizon_days=30, status="success",
        ))
        db.commit()
    finally:
        db.close()
    url = f"{API}/companies/{company_id}/forecast-runs"

    every = client.get(url, headers=headers)
    assert every.status_code == 200, every.text
    assert len(every.json()) == 4
    only_backtests = client.get(f"{url}?is_backtest=true", headers=headers).json()
    assert [r["is_backtest"] for r in only_backtests] == [True]
    real = client.get(f"{url}?is_backtest=false", headers=headers).json()
    assert len(real) == 3 and not any(r["is_backtest"] for r in real)
    paged = client.get(f"{url}?is_backtest=false&size=2&page=2", headers=headers).json()
    assert len(paged) == 1


# --- 6. created_at on reports -------------------------------------------------------
def test_reports_carry_created_at(
    client: TestClient, db_factory: sessionmaker[Session]  # noqa: F811
) -> None:
    headers, company_id, _ = _register(client, "p1", RUC_A)
    db = db_factory()
    try:
        repo = SqlReportRepository(db)
        saved = repo.add(Report(company_id=UUID(company_id), title="Ventas",
                                report_type=ReportType.KPI))
        assert saved.created_at is not None
        report_id = saved.id
        db.commit()
    finally:
        db.close()

    listed = client.get(f"{API}/companies/{company_id}/reports", headers=headers)
    assert listed.status_code == 200, listed.text
    item = listed.json()["items"][0]
    assert item["id"] == str(report_id)
    assert item["created_at"]
    one = client.get(f"{API}/companies/{company_id}/reports/{report_id}", headers=headers)
    assert one.json()["created_at"] == item["created_at"]
