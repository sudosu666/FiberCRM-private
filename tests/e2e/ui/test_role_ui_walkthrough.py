from __future__ import annotations

import os

import httpx
import pytest
from playwright.sync_api import Page, sync_playwright


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


def _require_backend() -> None:
    try:
        response = httpx.get(f"{BASE_URL}/health/live", timeout=3.0)
    except Exception as exc:
        pytest.skip(f"E2E backend is not reachable: {exc}")
    if response.status_code != 200:
        pytest.skip(f"E2E backend is not ready: {response.status_code}")


def login(page: Page, phone: str, password: str, expected_path: str) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    page.fill("#username", phone)
    page.fill("#password", password)
    page.click('button[type="submit"]')
    page.wait_for_url(f"**{expected_path}", timeout=10000)
    assert expected_path in page.url


def test_role_ui_walkthrough() -> None:
    _require_backend()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        scenarios = [
            ("dispatcher", "+38000000001", "dispatcher", "/dispatcher"),
            ("designer", "+38000000006", "designer", "/designer"),
            ("warehouse", "+38000000005", "warehouse", "/warehouse"),
            ("field", "+38000000002", "builder", "/field"),
        ]

        for role, phone, password, path in scenarios:
            page = browser.new_page()
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg, errs=console_errors: errs.append(msg.text)
                if msg.type == "error"
                else None,
            )
            page.on("pageerror", lambda exc, errs=console_errors: errs.append(str(exc)))

            login(page, phone, password, path)

            if role == "dispatcher":
                page.wait_for_selector("#tasksList", timeout=10000)
                page.click("#refreshTasks")
                page.fill("#groupName", "Playwright Brigade")
                page.select_option("#groupType", "construction")
                page.click("#createGroup")
                page.wait_for_timeout(800)
                assert page.locator("#brigadesList .task-item").count() >= 1

            elif role == "designer":
                page.wait_for_selector("input#addr", timeout=10000)
                page.fill("#addr", "Playwright UI Building")
                page.fill("#city", "Kyiv")
                page.fill("#dist", "140")
                page.click("text=Інфо для виконання")
                page.wait_for_selector("#executionPlan .task-item", timeout=10000)
                page.click("text=Зберегти план")
                page.wait_for_timeout(1000)

            elif role == "warehouse":
                page.wait_for_selector("#stockList", timeout=10000)
                page.fill("#adjustDelta", "1")
                page.fill("#adjustReason", "playwright-adjust")
                if page.locator("#adjustStockItem option").count() > 0:
                    page.select_option("#adjustStockItem", index=0)
                    page.click("#adjustStock")
                    page.wait_for_timeout(600)
                if page.locator("#requestStockItem option").count() > 0:
                    page.select_option("#requestStockItem", index=0)
                    page.fill("#requestQty", "1")
                    page.fill("#requestNote", "playwright-request")
                    page.click("#createRequest")
                    page.wait_for_timeout(600)

            elif role == "field":
                page.wait_for_selector("#taskList", timeout=10000)
                for selector in ["#refreshTasks", "#advanceStep", "#startTask", "#finishTask"]:
                    control = page.locator(selector)
                    if control.count() and control.first.is_visible():
                        control.first.click()
                        page.wait_for_timeout(250)
                hold_reason = page.locator("#holdReason")
                if hold_reason.count() and hold_reason.first.is_visible():
                    hold_reason.first.fill("playwright hold")
                    hold_button = page.locator("#holdTask")
                    if hold_button.count() and hold_button.first.is_visible():
                        hold_button.first.click()
                        page.wait_for_timeout(250)
                chat_input = page.locator("#chatInput")
                chat_send = page.locator('#chatForm button[type="submit"]')
                if chat_input.count() and chat_input.first.is_visible() and chat_send.count() and chat_send.first.is_visible():
                    chat_input.first.fill("playwright chat")
                    chat_send.first.click()
                    page.wait_for_timeout(500)

            assert console_errors == [], f"{role} console errors: {console_errors}"
            page.close()

        browser.close()
