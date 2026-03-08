from __future__ import annotations

import os

from playwright.sync_api import Page, sync_playwright


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


def login(page: Page, phone: str, password: str, expected_path: str) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    page.fill("#phone", phone)
    page.fill("#password", password)
    page.click('button[type="submit"]')
    page.wait_for_url(f"**{expected_path}", timeout=10000)
    assert expected_path in page.url


def test_role_ui_walkthrough() -> None:
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
                page.wait_for_selector("#tasksList .item, #tasksList .placeholder", timeout=10000)
                page.click("#refreshTasks")
                page.fill("#groupName", "Playwright Brigade")
                page.select_option("#groupType", "construction")
                if page.locator("#groupForeman option").count() > 1:
                    page.select_option("#groupForeman", index=1)
                if page.locator("#groupMembers option").count() > 0:
                    page.locator("#groupMembers option").nth(0).evaluate("el => el.selected = true")
                page.click("#createGroup")
                page.wait_for_timeout(800)
                if page.locator("[data-save-user]").count() > 0:
                    page.locator("[data-save-user]").first.click()
                    page.wait_for_timeout(500)

            elif role == "designer":
                page.wait_for_selector("input#addr", timeout=10000)
                page.fill("#addr", "Playwright UI Building")
                page.fill("#city", "Kyiv")
                page.click("text=Зберегти план")
                page.wait_for_timeout(1000)

            elif role == "warehouse":
                page.wait_for_selector("#stockList .item, #stockList .placeholder", timeout=10000)
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
                page.wait_for_selector("#taskList .task-card, #taskList .placeholder", timeout=10000)
                for selector in ["#refreshTasks", "#advanceStep", "#startTask", "#finishTask"]:
                    page.click(selector)
                    page.wait_for_timeout(250)
                page.fill("#holdReason", "playwright hold")
                page.click("#holdTask")
                page.wait_for_timeout(250)
                page.fill("#chatInput", "playwright chat")
                page.click('#chatForm button[type="submit"]')
                page.wait_for_timeout(500)

            assert console_errors == [], f"{role} console errors: {console_errors}"
            page.close()

        browser.close()
