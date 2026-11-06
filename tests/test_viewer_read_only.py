"""The viewer («Lector») role only reads: every change is refused except its own notices and preferences."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_audit_fixes import API, _create_user, _register, client, db_factory  # noqa: F401  (fixtures)


def test_viewer_reads_but_cannot_write(client: TestClient) -> None:  # noqa: F811
    owner, company_id, _ = _register(client, "v", "20222222222")
    # Users are created as seller or admin; the viewer role is given afterwards.
    user_id, viewer = _create_user(client, owner, company_id, "lector1", "seller")
    base = f"{API}/companies/{company_id}"
    assert client.patch(f"{base}/users/{user_id}/role", headers=owner, json={"role": "viewer"}).status_code == 200
    assert client.get(f"{base}/products", headers=viewer).status_code == 200
    res = client.post(f"{base}/suppliers", headers=viewer, json={"ruc": "20123456789", "business_name": "Proveedor X SAC"})
    assert res.status_code == 403, res.text
    assert "solo lectura" in res.text


def test_owner_still_writes(client: TestClient) -> None:  # noqa: F811
    owner, company_id, _ = _register(client, "w", "20333333333")
    res = client.post(f"{API}/companies/{company_id}/suppliers", headers=owner, json={"ruc": "20123456786", "business_name": "Proveedor Y SAC"})
    assert res.status_code in (200, 201), res.text
