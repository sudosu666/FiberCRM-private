from __future__ import annotations

import os

import httpx


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


def test_dispatcher_page_loads() -> None:
    response = httpx.get(f"{BASE_URL}/dispatcher", timeout=20.0)
    assert response.status_code == 200
    assert "dispatcher" in response.text.lower()


def test_field_page_loads() -> None:
    response = httpx.get(f"{BASE_URL}/field", timeout=20.0)
    assert response.status_code == 200
    assert "field" in response.text.lower()
