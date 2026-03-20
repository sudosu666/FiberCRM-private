from __future__ import annotations

import os

import httpx
import pytest


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture(autouse=True)
def require_e2e_backend() -> None:
    try:
        response = httpx.get(f"{BASE_URL}/health/live", timeout=3.0)
    except Exception as exc:
        pytest.skip(f"E2E backend is not reachable: {exc}")
    if response.status_code != 200:
        pytest.skip(f"E2E backend is not ready: {response.status_code}")
