from __future__ import annotations

import os

import httpx
import pytest
from playwright.sync_api import sync_playwright


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


def _require_backend() -> None:
    try:
        response = httpx.get(f"{BASE_URL}/health/live", timeout=3.0)
    except Exception as exc:
        pytest.skip(f"E2E backend is not reachable: {exc}")
    if response.status_code != 200:
        pytest.skip(f"E2E backend is not ready: {response.status_code}")


def _login_token(phone: str, password: str) -> str:
    response = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"phone": phone, "password": password},
        timeout=10.0,
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_panel_shows_demo_users() -> None:
    _require_backend()
    response = httpx.get(f"{BASE_URL}/auth/demo-users", timeout=10.0)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert any(user["phone"] == "+38000000006" for user in payload)


def test_designer_overview_and_execution_panels() -> None:
    _require_backend()
    token = _login_token("+38000000006", "designer")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        page.evaluate(
            "([t]) => { localStorage.setItem('fiberops_token', t); }",
            [token],
        )
        page.goto(f"{BASE_URL}/designer", wait_until="networkidle")

        page.wait_for_selector("#designMap", timeout=10000)
        page.wait_for_selector("#overviewSummary", timeout=10000)
        page.click("text=Інфо для виконання")
        page.wait_for_selector("#executionPlan .task-item", timeout=10000)

        # Required inputs for actual execution planning
        for selector in ["#addr", "#city", "#entr", "#floors", "#apts", "#pev", "#dist", "#extra", "#flH"]:
            assert page.locator(selector).count() == 1, f"Missing field: {selector}"

        browser.close()
