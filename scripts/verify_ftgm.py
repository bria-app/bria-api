"""End-to-end check of the Motor FTGM API (run inside the api container):

    docker compose exec -T api python scripts/verify_ftgm.py

Logs in as the PetHouse demo owner and exercises: ERP summary, scope preview
(recent_sales 12m), a scoped run (12m), a single-product run, a backtest run with a past
cut-off (so tracking has actual sales to compare), tracking + by-product + overview, and
free-plan gating (temporarily switches the subscription to free, then restores it).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, timedelta

import httpx
from sqlalchemy import select

sys.path.insert(0, ".")
import app.bootstrap.routers  # noqa: E402,F401
from app.modules.billing.infrastructure.persistence.models import SubscriptionModel  # noqa: E402
from app.shared.infrastructure.database import SessionLocal  # noqa: E402

BASE = "http://localhost:8000/api/v1"
c = httpx.Client(base_url=BASE, timeout=240)


def check(resp: httpx.Response, expected: int = 200) -> dict | list:
    if resp.status_code != expected:
        print(f"FAIL {resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text[:600]}")
        sys.exit(1)
    return resp.json()


def wait_run(cid: str, run_id: str, label: str) -> dict:
    t0 = time.time()
    while True:
        run = check(c.get(f"/companies/{cid}/forecast-runs/{run_id}"))
        if run["status"] in ("success", "failed", "cancelled"):
            print(f"[{label}] status={run['status']} in {time.time() - t0:.1f}s error={run['error_message']}")
            print(f"[{label}] summary={json.dumps(run['summary'])}")
            if run["status"] != "success":
                sys.exit(1)
            return run
        if time.time() - t0 > 600:
            sys.exit(f"[{label}] timeout")
        time.sleep(2)


def main() -> None:
    password = os.getenv("DEMO_OWNER_PASSWORD")
    if not password:
        sys.exit("Define DEMO_OWNER_PASSWORD con la clave que usaste al cargar la demo.")
    tok = check(c.post("/auth/login", json={"email": "demo@pethouse.pe", "password": password}))
    c.headers["Authorization"] = f"Bearer {tok['access_token']}"
    me = check(c.get("/auth/me"))
    cid = me["company_id"]

    erp = check(c.get(f"/companies/{cid}/dashboard/erp-summary"))
    print("[erp-summary]", {k: erp[k] for k in (
        "revenue_today", "revenue_7d", "revenue_30d", "tickets_30d", "avg_ticket_30d", "inventory_value",
        "low_stock_count", "out_of_stock_count", "purchases_month_total", "lost_sales_30d_attempts",
        "lost_sales_30d_units")}, "top:", [p["name"] for p in erp["top_products"][:3]])

    scope = {"type": "recent_sales", "months": 12}
    prev = check(c.post(f"/companies/{cid}/forecast-runs/scope-preview", json={"scope": scope, "frequency": "auto"}))
    t = prev["totals"]
    print("[preview 12m]", {k: t[k] for k in (
        "description", "frequency", "products_total", "products_included", "products_ready", "products_low_data",
        "total_data_points", "date_start", "date_end")})
    for p in prev["products"][:30]:
        print(f"   - {p['sku']:<10} {p['readiness']:<12} {p['frequency'] or '-':<8} per={p['periods']:<4} "
              f"units={p['total_units']:<6} restocks={p['restocks_count']:<3} stockout_per={p['stockout_periods']:<3} "
              f"lost={p['lost_sale_attempts']:<3} {p['reason'][:70]}")

    run = check(c.post(f"/companies/{cid}/forecast-runs", json={"scope": scope, "horizon_days": 90, "frequency": "auto"}), 201)
    run = wait_run(cid, run["id"], "run 12m")
    ov = check(c.get(f"/companies/{cid}/forecast-runs/{run['id']}/overview"))
    print("[overview 12m]", ov["summary"])
    for p in ov["products"]:
        h = p["holdout"] or {}
        print(f"   - {p['sku']:<10} {p['model_used']:<14} N={p['order_selected']} freq={p['frequency']:<7} "
              f"holdoutMAPE={h.get('mape')} skill={p['skill_vs_naive']} next={p['next_period_units']} "
              f"risk={p['stockout_risk']} qty={p['suggested_qty']}")
    first = ov["products"][0]["product_id"]
    diag = ov["diagnostics"][first]
    print("[diagnostics sample]", json.dumps(diag.get("explanations"), ensure_ascii=False, indent=1))
    tr = check(c.get(f"/companies/{cid}/forecast-runs/{run['id']}/tracking"))
    print("[tracking new run]", {k: tr[k] for k in ("forecast_to_date", "actual_to_date", "products_pending")})

    # Single product (what a free user can do).
    single = {"type": "products", "product_ids": [first]}
    r1 = check(c.post(f"/companies/{cid}/forecast-runs", json={"scope": single, "horizon_days": 30}), 201)
    wait_run(cid, r1["id"], "single product")

    # Backtest: history cut 6 months ago -> tracking compares with real sales since then.
    as_of = (date.today() - timedelta(days=183)).replace(day=1)
    rb = check(c.post(f"/companies/{cid}/forecast-runs", json={
        "scope": scope, "horizon_days": 180, "frequency": "monthly", "as_of": as_of.isoformat()}), 201)
    rb = wait_run(cid, rb["id"], f"backtest as_of={as_of}")
    trb = check(c.get(f"/companies/{cid}/forecast-runs/{rb['id']}/tracking"))
    print("[tracking backtest]", {k: trb[k] for k in (
        "as_of", "forecast_to_date", "actual_to_date", "bias_pct", "products_on_track", "products_over",
        "products_under", "products_pending")})
    for p in trb["products"][:6]:
        print(f"   - {p['sku']:<10} status={p['status']:<17} MAPE={p['mape']} bias={p['bias_pct']} "
              f"complete={p['periods_complete']} band={p['within_band_share']}")
    byp = check(c.get(f"/companies/{cid}/forecast-runs/by-product/{first}"))
    print("[by-product]", [(e["run"]["scope_description"], (e["tracking"] or {}).get("status")) for e in byp])
    ins = check(c.get(f"/companies/{cid}/forecast-runs/product-insight/{first}?frequency=weekly&periods=26"))
    print("[insight]", ins["name"], "ledger_reliable=", ins["ledger_reliable"], "periods=", len(ins["periods"]),
          "restocks=", len(ins["restocks"]), "stockout_weeks=", sum(1 for x in ins["periods"] if x["stockout_days"]))

    # KPIs + recommendations from the new runs.
    recs = check(c.get(f"/companies/{cid}/recommendations?pending_only=true"))
    kpis = check(c.get(f"/companies/{cid}/kpis?size=100"))
    print("[decision layer] pending recs:", len(recs), "kpi rows:", len(kpis))

    # Free-plan gating.
    db = SessionLocal()
    sub = db.execute(select(SubscriptionModel).where(SubscriptionModel.company_id == cid)).scalar_one_or_none()
    original = (sub.plan_id, sub.status) if sub else None
    try:
        if sub:
            sub.plan_id, sub.status = "free", "active"
            db.commit()
        multi = c.post(f"/companies/{cid}/forecast-runs", json={"scope": scope, "horizon_days": 30})
        print("[gating free multi-product]", multi.status_code, multi.json().get("message"))
        prev1 = c.post(f"/companies/{cid}/forecast-runs/scope-preview", json={"scope": single})
        print("[gating free single preview]", prev1.status_code)
        assert multi.status_code == 403 and prev1.status_code == 200
    finally:
        if sub and original:
            sub = db.execute(select(SubscriptionModel).where(SubscriptionModel.company_id == cid)).scalar_one()
            sub.plan_id, sub.status = original
            db.commit()
            print("[gating] subscription restored to", original)
        db.close()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
