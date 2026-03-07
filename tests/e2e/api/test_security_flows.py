from __future__ import annotations

import base64
import os
import uuid

import httpx


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
AUTH_LIMIT = int(os.getenv("RATE_LIMIT_AUTH_PER_MINUTE", "10"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "2000000"))


def _login(phone: str = "+38000000001", password: str = "dispatcher") -> httpx.Response:
    return httpx.post(
        f"{BASE_URL}/token",
        data={"username": phone, "password": password},
        timeout=20.0,
    )


def test_health_endpoints() -> None:
    live = httpx.get(f"{BASE_URL}/health/live", timeout=20.0)
    ready = httpx.get(f"{BASE_URL}/health/ready", timeout=20.0)
    assert live.status_code == 200
    assert ready.status_code == 200
    assert live.json()["status"] == "live"
    assert ready.json()["status"] == "ready"


def test_auth_success_and_failure() -> None:
    ok = _login()
    assert ok.status_code == 200
    assert "access_token" in ok.json()

    bad = _login(password="wrong-pass")
    assert bad.status_code == 401


def test_auth_rate_limit() -> None:
    username = f"rate-limit-{uuid.uuid4().hex[:8]}"
    statuses: list[int] = []
    for _ in range(AUTH_LIMIT + 2):
        resp = httpx.post(
            f"{BASE_URL}/token",
            data={"username": username, "password": "wrong-pass"},
            timeout=20.0,
        )
        statuses.append(resp.status_code)
    assert 429 in statuses


def test_report_upload_size_limit() -> None:
    tasks = httpx.get(f"{BASE_URL}/api/tasks", timeout=20.0)
    assert tasks.status_code == 200
    task_id = tasks.json()[0]["id"]

    raw = b"x" * (MAX_UPLOAD_BYTES + 128)
    payload = base64.b64encode(raw).decode("ascii")
    body = {
        "photo_filename": "big.png",
        "photo_data": payload,
        "comment": "oversize test",
    }
    resp = httpx.post(f"{BASE_URL}/api/tasks/{task_id}/reports", json=body, timeout=20.0)
    assert resp.status_code in (400, 413)
