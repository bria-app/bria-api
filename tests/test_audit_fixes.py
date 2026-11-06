"""Regression tests for the code-audit fixes (AUDITORIA_CODIGO.md, 02/11/2026).

C-01 simulated billing webhook · C-02 user role/disable rules · C-03 demo credentials ·
C-04 honest mock engine + engine mode exposure + production guard · M-01 completion
notification text · A-02 per-request user re-validation and seller writes · A-03 JWT
secret validator · M-05 timeout + stale runs · M-10 nullable metrics · M-14 plan quota
on the legacy run path · B-02 docs off in production · engine shared key header.
Cross-tenant id routes (A-01) live in test_tenant_isolation.py.
"""
from __future__ import annotations

import importlib.util
from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, settings
from app.modules.forecasting.application.dtos import run_engine_mode
from app.modules.forecasting.application.ports import ProductForecast
from app.modules.forecasting.application.use_cases.execution import (
    completion_message,
    summarize,
)
from app.modules.forecasting.domain.entities import ForecastRun
from app.modules.forecasting.infrastructure.adapters.ftgm_adapter import FtgmHttpAdapter
from app.modules.forecasting.infrastructure.adapters.mock_ftgm import (
    MOCK_MODEL,
    MOCK_NOTICE,
    MockFtgmAdapter,
    _PROFILES,
)

API = "/api/v1"
ROOT = Path(__file__).resolve().parents[1]
STRONG_SECRET = "s" * 48


# --- fixtures -----------------------------------------------------------------
@pytest.fixture()
def db_factory() -> Generator[sessionmaker[Session], None, None]:
    from app.modules.companies.infrastructure.persistence import models  # noqa: F401
    from app.shared.infrastructure.database import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    from app.main import app
    from app.shared.infrastructure.database import get_db

    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)  # no lifespan: the real database is never touched
    app.dependency_overrides.clear()


def _register(client: TestClient, suffix: str, tax_id: str) -> tuple[dict[str, str], str, str]:
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
    me = client.get(f"{API}/auth/me", headers=headers).json()
    return headers, me["company_id"], me["id"]


def _create_user(
    client: TestClient, headers: dict[str, str], company_id: str, username: str, role: str
) -> tuple[str, dict[str, str]]:
    res = client.post(
        f"{API}/companies/{company_id}/users",
        headers=headers,
        json={"full_name": username, "username": username, "password": "secret123", "role": role},
    )
    assert res.status_code == 201, res.text
    login = client.post(f"{API}/auth/login", json={"identifier": username, "password": "secret123"})
    assert login.status_code == 200, login.text
    return res.json()["id"], {"Authorization": f"Bearer {login.json()['access_token']}"}


# --- C-01: simulated billing webhook ----------------------------------------------
class TestSimulatedWebhook:
    def _url(self, company_id: str) -> str:
        return f"{API}/billing/webhooks/simulate/{company_id}"

    def test_requires_authentication(self, client: TestClient) -> None:
        res = client.post(self._url(str(uuid4())), json={"status": "active", "plan_id": "premium"})
        assert res.status_code == 401

    def test_other_company_is_forbidden(self, client: TestClient) -> None:
        headers_a, _, _ = _register(client, "a", "20111111111")
        _, company_b, _ = _register(client, "b", "20222222222")
        res = client.post(self._url(company_b), headers=headers_a, json={"status": "active", "plan_id": "premium"})
        assert res.status_code == 403

    def test_seller_is_forbidden_and_owner_allowed(self, client: TestClient) -> None:
        headers, company_id, _ = _register(client, "a", "20111111111")
        _, seller = _create_user(client, headers, company_id, "caja1", "seller")
        body = {"status": "active", "plan_id": "premium"}
        assert client.post(self._url(company_id), headers=seller, json=body).status_code == 403
        ok = client.post(self._url(company_id), headers=headers, json=body)
        assert ok.status_code == 200, ok.text
        assert ok.json()["plan_id"] == "premium"

    def test_not_registered_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.modules.billing.presentation import router as billing_router

        monkeypatch.setattr(settings, "app_env", "production")
        assert billing_router.simulate_webhook_enabled() is False
        monkeypatch.setattr(settings, "app_env", "development")
        assert billing_router.simulate_webhook_enabled() is True


# --- C-02: user role / disable rules ------------------------------------------------
class TestUserManagementRules:
    def test_admin_cannot_promote_to_owner_or_touch_owner_or_self(self, client: TestClient) -> None:
        owner_headers, company_id, owner_id = _register(client, "a", "20111111111")
        admin_id, admin = _create_user(client, owner_headers, company_id, "admin1", "admin")
        seller_id, _ = _create_user(client, owner_headers, company_id, "caja1", "seller")
        users = f"{API}/companies/{company_id}/users"

        to_owner = client.patch(f"{users}/{seller_id}/role", headers=admin, json={"role": "owner"})
        assert to_owner.status_code == 403, to_owner.text
        assert client.patch(f"{users}/{owner_id}/role", headers=admin, json={"role": "viewer"}).status_code == 403
        assert client.delete(f"{users}/{owner_id}", headers=admin).status_code == 403
        assert client.patch(f"{users}/{admin_id}/role", headers=admin, json={"role": "analyst"}).status_code == 403
        assert client.delete(f"{users}/{admin_id}", headers=admin).status_code == 403

        ok = client.patch(f"{users}/{seller_id}/role", headers=admin, json={"role": "analyst"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["role"] == "analyst"
        disabled = client.delete(f"{users}/{seller_id}", headers=owner_headers)
        assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"

    def test_other_company_user_is_not_found(self, client: TestClient) -> None:
        headers_a, company_a, _ = _register(client, "a", "20111111111")
        headers_b, company_b, _ = _register(client, "b", "20222222222")
        seller_b, _ = _create_user(client, headers_b, company_b, "cajab", "seller")
        # Owner of A uses its own company in the path but B's user id.
        res = client.patch(
            f"{API}/companies/{company_a}/users/{seller_b}/role", headers=headers_a, json={"role": "viewer"}
        )
        assert res.status_code == 404
        assert client.delete(f"{API}/companies/{company_a}/users/{seller_b}", headers=headers_a).status_code == 404


# --- A-02: re-validation against the DB + seller writes ------------------------------
class TestCurrentUserRevalidation:
    def test_disabled_user_token_stops_working_immediately(self, client: TestClient) -> None:
        owner, company_id, _ = _register(client, "a", "20111111111")
        seller_id, seller = _create_user(client, owner, company_id, "caja1", "seller")
        assert client.get(f"{API}/auth/me", headers=seller).status_code == 200
        client.delete(f"{API}/companies/{company_id}/users/{seller_id}", headers=owner)
        assert client.get(f"{API}/auth/me", headers=seller).status_code == 401

    def test_demoted_admin_loses_admin_rights_with_the_same_token(self, client: TestClient) -> None:
        owner, company_id, _ = _register(client, "a", "20111111111")
        admin_id, admin = _create_user(client, owner, company_id, "admin1", "admin")
        users = f"{API}/companies/{company_id}/users"
        body = {"full_name": "x", "username": "nuevo1", "password": "secret123", "role": "seller"}
        assert client.post(users, headers=admin, json=body).status_code == 201
        client.patch(f"{users}/{admin_id}/role", headers=owner, json={"role": "viewer"})
        body["username"] = "nuevo2"
        assert client.post(users, headers=admin, json=body).status_code == 403

    def test_seller_writes_limited_to_till(self, client: TestClient) -> None:
        owner, company_id, _ = _register(client, "a", "20111111111")
        _, seller = _create_user(client, owner, company_id, "caja1", "seller")
        base = f"{API}/companies/{company_id}"
        product = client.post(
            f"{base}/products", headers=owner, json={"name": "Polo", "unit_price": "10", "initial_stock": 20}
        ).json()
        sale = client.post(
            f"{base}/sales",
            headers=owner,
            json={"product_id": product["id"], "sale_date": date.today().isoformat(), "quantity": 1, "unit_price": "10"},
        ).json()

        assert client.delete(f"{base}/sales/{sale['id']}", headers=seller).status_code == 403
        bulk = {"items": [{"product_id": product["id"], "sale_date": date.today().isoformat(), "quantity": 1, "unit_price": "10"}]}
        assert client.post(f"{base}/sales/bulk", headers=seller, json=bulk).status_code == 403
        assert client.post(
            f"{base}/invoices",
            headers=seller,
            json={"document_type": "boleta", "items": [{"description": "x", "quantity": 1, "unit_price": "1"}]},
        ).status_code == 403

        order = client.post(
            f"{base}/sales-orders",
            headers=seller,
            json={"items": [{"product_id": product["id"], "quantity": 1, "unit_price": "10"}]},
        )
        assert order.status_code == 201, order.text
        lost = client.post(
            f"{base}/lost-sales", headers=seller, json={"product_id": product["id"], "requested_quantity": 2}
        )
        assert lost.status_code == 201, lost.text
        assert client.get(f"{base}/sales", headers=seller).status_code == 200


# --- C-03: demo credentials from the environment ---------------------------------------
def _load_bootstrap() -> Any:
    spec = importlib.util.spec_from_file_location("bootstrap_demo_under_test", ROOT / "scripts" / "bootstrap_demo.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDemoCredentials:
    def test_env_vars_win(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEMO_OWNER_PASSWORD", "Owner-Rotated-1")
        monkeypatch.setenv("DEMO_SELLER_PASSWORD", "Seller-Rotated-1")
        assert _load_bootstrap().demo_passwords() == ("Owner-Rotated-1", "Seller-Rotated-1")

    def test_seeding_is_skipped_without_both_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEMO_OWNER_PASSWORD", raising=False)
        monkeypatch.setenv("DEMO_SELLER_PASSWORD", "only-one-set")
        assert _load_bootstrap().demo_passwords() is None

    def test_no_password_literal_in_the_code(self) -> None:
        source = (ROOT / "scripts" / "bootstrap_demo.py").read_text(encoding="utf-8")
        assert "OWNER_PASSWORD = " not in source
        assert "_DEV_" not in source


# --- C-04: honest mock engine + mode exposure + production guard ------------------------
class _Point:
    def __init__(self, day: date, qty: float) -> None:
        self.period_date = day
        self.demand = Decimal(str(qty))


class _Series:
    def __init__(self, product_id: Any, points: list[_Point]) -> None:
        self.product_id = product_id
        self.points = points


def _mock_forecast() -> ProductForecast:
    today = date(2026, 9, 20)
    series = _Series(uuid4(), [_Point(today - timedelta(days=d), 3) for d in range(1, 200)])
    return MockFtgmAdapter(None)._one(series, 30, "auto", today, _PROFILES["general"])  # type: ignore[arg-type]


class TestHonestMock:
    def test_mock_never_fabricates_measurements(self) -> None:
        f = _mock_forecast()
        d = f.diagnostics
        assert d["accuracy_pct"] is None
        assert d["candidates"] == []
        assert d["skill_vs_naive"] is None
        assert d["holdout"] is None
        assert (f.mape, f.mae, f.rmse, f.mase, f.rmsse, f.validation_rmse) == (None,) * 6
        assert f.model_used == MOCK_MODEL == "DEMO"
        assert d["engine"] == "mock"
        assert "DEMOSTRACI" in MOCK_NOTICE and d["mock_notice"] == MOCK_NOTICE
        assert f.points  # it still projects something to show

    def test_summary_and_dto_expose_engine_mode(self) -> None:
        summary = summarize([_mock_forecast()], "mock")
        assert summary["ftgm_engine_mode"] == "mock"
        assert summary["median_accuracy_pct"] is None
        assert summary["models"] == {"DEMO": 1}

        run = ForecastRun(company_id=uuid4(), model_name="FTGM", horizon_days=30, dataset_id=None)
        run.set_meta(diagnostics={str(uuid4()): {"engine": "mock"}})  # run older than the field
        assert run_engine_mode(run) == "mock"
        run.set_meta(summary={"ftgm_engine_mode": "real"})
        assert run_engine_mode(run) == "real"

    def test_health_and_status_expose_the_mode(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "ftgm_engine_mode", "mock")
        root = client.get("/health").json()
        assert root == {"status": "ok", "ftgm_engine_mode": "mock"}
        assert client.get(f"{API}/health").json()["ftgm_engine_mode"] == "mock"
        status = client.get(f"{API}/status").json()
        assert status["ftgm_engine_mode"] == "mock"
        assert status["dependencies"]["ftgm_engine"].startswith("mock")

    def test_production_refuses_mock_unless_overridden(self) -> None:
        from app.main import UnsafeConfigurationError, check_ftgm_engine_mode

        prod_mock = Settings(app_env="production", ftgm_engine_mode="mock", jwt_secret_key=STRONG_SECRET)
        with pytest.raises(UnsafeConfigurationError):
            check_ftgm_engine_mode(prod_mock)
        check_ftgm_engine_mode(
            Settings(app_env="production", ftgm_engine_mode="mock", allow_ftgm_mock=True, jwt_secret_key=STRONG_SECRET)
        )
        check_ftgm_engine_mode(Settings(app_env="production", ftgm_engine_mode="real", jwt_secret_key=STRONG_SECRET))
        check_ftgm_engine_mode(Settings(app_env="development", ftgm_engine_mode="mock"))


# --- M-01: completion notification ------------------------------------------------------
class TestCompletionMessage:
    def test_never_attributes_the_run_to_one_model(self) -> None:
        title, text = completion_message({"models": {"FTGM": 3, "FTGMCombo": 1, "DampedTrend": 2, "CrostonSBA": 1}})
        assert title == "Tu pronóstico está listo"
        assert text == "7 productos pronosticados. Cada uno usa el método que mejor acertó con sus ventas."
        # Plain words for the owner: no model names at all.
        for model in ("FTGM", "DampedTrend", "CrostonSBA"):
            assert model not in text

    def test_one_and_none(self) -> None:
        assert completion_message({"models": {"FTGM": 1}})[1] == "1 producto pronosticado. Usa el método que mejor acertó con sus ventas."
        assert "Ningún producto" in completion_message({"models": {}})[1]

    def test_mock_run_is_labelled_as_demo(self) -> None:
        title, text = completion_message({"models": {"DEMO": 5}, "ftgm_engine_mode": "mock"})
        assert "demostración" in title.lower() and "FTGM en" not in text


# --- A-03: JWT secret validator -----------------------------------------------------
class TestJwtSecretValidator:
    @pytest.mark.parametrize(
        "secret", ["change-this-in-production", "change-this-in-production-use-a-strong-secret", "short-secret"]
    )
    def test_weak_secret_rejected_outside_dev(self, secret: str) -> None:
        with pytest.raises(PydanticValidationError):
            Settings(app_env="production", jwt_secret_key=secret)
        with pytest.raises(PydanticValidationError):
            Settings(app_env="staging", jwt_secret_key=secret)

    def test_strong_secret_and_local_envs_accepted(self) -> None:
        assert Settings(app_env="production", jwt_secret_key=STRONG_SECRET).is_production
        Settings(app_env="development", jwt_secret_key="change-this-in-production")
        Settings(app_env="test", jwt_secret_key="x")


# --- B-02: docs disabled in production ------------------------------------------------
def test_docs_and_schema_hidden_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    monkeypatch.setattr(settings, "app_env", "production")
    prod = TestClient(create_app())
    assert prod.get("/docs").status_code == 404
    assert prod.get("/openapi.json").status_code == 404
    monkeypatch.setattr(settings, "app_env", "development")
    dev = TestClient(create_app())
    assert dev.get("/openapi.json").status_code == 200


# --- engine contract: shared key + timeout (A-06 API side, M-05) ------------------------
class TestFtgmHttpAdapter:
    def test_sends_engine_key_and_respects_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        class _Response:
            def raise_for_status(self) -> None: ...

            def json(self) -> dict[str, Any]:
                return {"forecasts": []}

        def fake_post(url: str, **kwargs: Any) -> _Response:
            captured.update(kwargs, url=url)
            return _Response()

        monkeypatch.setattr("httpx.post", fake_post)
        FtgmHttpAdapter(base_url="http://engine/api/v1", timeout=30, api_key="k-123").forecast(
            series=[], horizon_days=30, model_name="FTGM"
        )
        assert captured["headers"] == {"X-Engine-Key": "k-123"}
        assert captured["timeout"] == 30  # no hidden 180 s floor any more

    def test_no_header_without_key(self) -> None:
        assert FtgmHttpAdapter(api_key="").headers() == {}

    def test_null_metrics_stay_null(self) -> None:
        parsed = FtgmHttpAdapter._parse(
            {"product_id": str(uuid4()), "points": [], "metrics": {"mape": None, "mae": 1.5}}
        )
        assert parsed.mape is None and parsed.rmse is None
        assert parsed.mae == Decimal("1.5")


# --- M-05: stale runs failed at startup ----------------------------------------------
def test_fail_stale_runs(db_factory: sessionmaker[Session]) -> None:
    from app.modules.forecasting.infrastructure.background import STALE_RUN_MESSAGE, fail_stale_runs
    from app.modules.forecasting.infrastructure.persistence.models import ForecastRunModel

    now = datetime.now(timezone.utc)
    company = uuid4()

    def run(status: str, started: datetime | None) -> ForecastRunModel:
        return ForecastRunModel(
            company_id=company, model_name="FTGM", horizon_days=30, status=status, started_at=started
        )

    with db_factory() as session:
        old, fresh, done = run("running", now - timedelta(hours=2)), run("running", now - timedelta(minutes=5)), run(
            "success", now - timedelta(hours=3)
        )
        session.add_all([old, fresh, done])
        session.commit()
        assert fail_stale_runs(session) == 1
        session.commit()
        session.refresh(old)
        session.refresh(fresh)
        session.refresh(done)
        assert old.status == "failed" and old.error_message == STALE_RUN_MESSAGE
        assert fresh.status == "running"
        assert done.status == "success"


# --- M-10: metrics persisted as NULL ------------------------------------------------------
def test_metrics_null_round_trip(db_factory: sessionmaker[Session]) -> None:
    from app.modules.forecasting.domain.entities import ForecastMetrics
    from app.modules.forecasting.infrastructure.persistence.repositories import SqlForecastMetricsRepository

    run_id = uuid4()
    with db_factory() as session:
        repo = SqlForecastMetricsRepository(session)
        repo.add(ForecastMetrics(run_id=run_id, product_id=uuid4(), mape=None, mae=None, rmse=None))
        session.commit()
        (stored,) = repo.list_by_run(run_id)
    assert stored.mape is None and stored.mae is None and stored.rmse is None


# --- M-14: the legacy CSV run path also counts against the free quota -----------------------
def test_legacy_run_path_enforces_plan(client: TestClient, db_factory: sessionmaker[Session]) -> None:
    from app.modules.forecasting.infrastructure.persistence.repositories import SqlForecastRunRepository
    from app.modules.forecasting.infrastructure.plan import FREE_MONTHLY_RUNS

    headers, company_id, _ = _register(client, "a", "20111111111")
    with db_factory() as session:
        repo = SqlForecastRunRepository(session)
        for _ in range(FREE_MONTHLY_RUNS):
            repo.add(ForecastRun(company_id=UUID(company_id), model_name="FTGM", horizon_days=30, dataset_id=None))
        session.commit()
    res = client.post(
        f"{API}/companies/{company_id}/forecast-runs",
        headers=headers,
        json={"model_name": "FTGM", "horizon_days": 30},
    )
    assert res.status_code == 403, res.text
    assert res.json()["details"]["plan"] == "free"
