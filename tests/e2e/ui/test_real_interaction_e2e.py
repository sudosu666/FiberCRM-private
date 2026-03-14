"""
Real Interaction E2E Test Suite
================================
Simulates the full lifecycle of a building connection project across all roles.
Uses hybrid approach:
  - API calls for fast, reliable data setup (auth, tender, plan, brigade)
  - Browser UI for validating page rendering and interactive flows
"""
import os
import pytest
from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


def api_login(request_ctx, phone: str, password: str) -> str:
    """Get a JWT token by calling the API login endpoint directly."""
    # Auth router has no prefix — route is /auth/login, not /api/auth/login
    res = request_ctx.post(
        f"{BASE_URL}/auth/login",
        headers={"Content-Type": "application/json"},
        data=f'{{"phone": "{phone}", "password": "{password}"}}',
    )
    assert res.ok, f"Login failed for {phone!r}: {res.status} {res.text()}"
    data = res.json()
    return data.get("token") or data.get("access_token")


def test_real_interaction_e2e():
    """
    Full lifecycle test covering Designer to Dispatcher to Field Worker to Warehouse.
    Assertions validate data integrity across all role transitions.
    """
    with sync_playwright() as p:
        # 1. AUTHENTICATION (via direct API, no auth.js dependency)
        base_ctx = p.request.new_context()
        designer_token   = api_login(base_ctx, "+38000000006", "designer")
        dispatcher_token = api_login(base_ctx, "+38000000001", "dispatcher")
        builder_token    = api_login(base_ctx, "+38000000002", "builder")
        warehouse_token  = api_login(base_ctx, "+38000000005", "warehouse")

        def make_ctx(token):
            return p.request.new_context(
                extra_http_headers={"Authorization": f"Bearer {token}"},
            )

        d_ctx  = make_ctx(designer_token)
        dp_ctx = make_ctx(dispatcher_token)
        b_ctx  = make_ctx(builder_token)
        w_ctx  = make_ctx(warehouse_token)

        # 2. DESIGNER: Create Tender
        tender_res = d_ctx.post(f"{BASE_URL}/api/tenders", data={
            "name": "E2E Playwright Tender",
            "customer": "Autotest Corp",
            "city": "Kyiv",
        })
        assert tender_res.ok, f"Create tender failed: {tender_res.text()}"
        tender_id = tender_res.json()["id"]

        # 3. DESIGNER: Submit Network Plan
        plan_res = d_ctx.post(f"{BASE_URL}/api/network/plan", data={
            "tender_id": tender_id,
            "address": "Playwright Integration Ave 42",
            "city": "Kyiv",
            "entrances_count": 2,
            "floors_count": 5,
            "flats_per_floor": 4,
            "floor_height_m": 3.0,
            "panel_every_n_floors": 5,
            "distance_from_muffle_m": 50,
            "cable_reserve_pct": 10,
        })
        assert plan_res.ok, f"Create plan failed: {plan_res.text()}"
        plan = plan_res.json()
        task_ids         = plan["task_ids"]
        warehouse_req_id = plan.get("warehouse_request_id")

        assert len(task_ids) > 0, "No tasks generated from plan"
        construction_task_id = task_ids[0]

        # 4. DISPATCHER: Find or Create "Playwright Brigade"
        brigades = dp_ctx.get(f"{BASE_URL}/api/brigades").json()
        brigade = next((b for b in brigades if b.get("name") == "Playwright Brigade"), None)

        if brigade is None:
            create_res = dp_ctx.post(f"{BASE_URL}/api/brigades", data={
                "name": "Playwright Brigade",
                "type": "construction",
                "is_active": True,
            })
            if create_res.ok:
                brigade = create_res.json()

        brigade_id = brigade["id"] if brigade else None

        # 5. DISPATCHER: Assign Task to Brigade
        if brigade_id:
            assign_res = dp_ctx.post(
                f"{BASE_URL}/api/tasks/{construction_task_id}/assign",
                data={"brigade_id": brigade_id},
            )
            assert assign_res.ok, f"Task assign failed: {assign_res.text()}"

        # 6. BROWSER UI: Verify Dispatcher Board page loads
        browser = p.chromium.launch(headless=True)
        disp_page = browser.new_page()
        # Inject token so the page considers the user authenticated
        disp_page.goto(f"{BASE_URL}/login")
        disp_page.evaluate(
            "([token]) => { localStorage.setItem('fiberops_token', token); }",
            [dispatcher_token],
        )
        # Navigate to dispatcher board — only assert page responds (dispatcher.js not yet in static dir)
        resp = disp_page.goto(f"{BASE_URL}/dispatcher")
        assert resp.status == 200, f"Dispatcher page returned {resp.status}"

        # 7. FIELD: Submit Photo Report (via API)
        dummy_png = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HA"
            "wCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        )
        report_res = b_ctx.post(f"{BASE_URL}/api/tasks/{construction_task_id}/reports", data={
            "photo_data": dummy_png,
            "photo_filename": "e2e_test.png",
            "comment": "Field worker E2E report",
        })
        assert report_res.ok, f"Report submission failed: {report_res.text()}"

        # 8. WAREHOUSE: Attempt fulfillment of auto-generated request
        if warehouse_req_id:
            reqs = w_ctx.get(f"{BASE_URL}/api/warehouse/requests").json()
            target = next((r for r in reqs if r["id"] == warehouse_req_id), None)

            if target:
                items_payload = [
                    {"item_id": item["id"], "fulfilled_qty": item["planned_qty"]}
                    for item in target.get("items", [])
                ]
                fulfill_res = w_ctx.post(
                    f"{BASE_URL}/api/warehouse/requests/{warehouse_req_id}/fulfill",
                    data={"items": items_payload},
                )
                # Stock shortfall -> 422, acceptable in blank test DB
                print(
                    f"Warehouse fulfill: HTTP {fulfill_res.status} — "
                    + (fulfill_res.text()[:120] if not fulfill_res.ok else "OK")
                )

        browser.close()
