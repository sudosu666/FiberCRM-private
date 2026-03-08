from __future__ import annotations

import os
import uuid

import httpx


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


def _login(phone: str, password: str) -> dict[str, str]:
    response = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"phone": phone, "password": password},
        timeout=20.0,
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_full_role_flow_plan_to_field() -> None:
    designer = _login("+38000000006", "designer")
    warehouse = _login("+38000000005", "warehouse")
    dispatcher = _login("+38000000001", "dispatcher")
    builder = _login("+38000000002", "builder")

    address = f"role-flow-{uuid.uuid4().hex[:8]}"
    plan = {
        "tender_id": None,
        "address": address,
        "city": "Kyiv",
        "entrances_count": 1,
        "floors_count": 3,
        "flats_per_floor": 2,
        "floor_height_m": 2.8,
        "panel_every_n_floors": 2,
        "distance_from_muffle_m": 30,
        "cable_reserve_pct": 10,
        "muffle_id": None,
        "selected_fibers": [],
    }

    plan_response = httpx.post(
        f"{BASE_URL}/api/network/plan",
        headers=designer,
        json=plan,
        timeout=20.0,
    )
    assert plan_response.status_code == 201
    plan_payload = plan_response.json()
    assert len(plan_payload["task_ids"]) == 3
    assert plan_payload["warehouse_request_id"] is not None

    requests_response = httpx.get(
        f"{BASE_URL}/api/warehouse/requests",
        headers=warehouse,
        timeout=20.0,
    )
    assert requests_response.status_code == 200
    assert any(req["id"] == plan_payload["warehouse_request_id"] for req in requests_response.json())

    brigades_response = httpx.get(
        f"{BASE_URL}/api/brigades",
        headers=dispatcher,
        timeout=20.0,
    )
    assert brigades_response.status_code == 200
    workers_response = httpx.get(
        f"{BASE_URL}/api/field/workers",
        headers=dispatcher,
        timeout=20.0,
    )
    assert workers_response.status_code == 200
    builder_user = next(worker for worker in workers_response.json() if worker["phone"] == "+38000000002")
    brigade_id = builder_user["brigade_id"]
    assert brigade_id is not None

    assign_response = httpx.post(
        f"{BASE_URL}/api/tasks/{plan_payload['task_ids'][0]}/assign",
        headers=dispatcher,
        json={"brigade_id": brigade_id},
        timeout=20.0,
    )
    assert assign_response.status_code == 200
    assert assign_response.json()["status"] == "assigned"

    field_tasks = httpx.get(
        f"{BASE_URL}/api/tasks",
        headers=builder,
        timeout=20.0,
    )
    assert field_tasks.status_code == 200
    assert any(task["id"] == plan_payload["task_ids"][0] for task in field_tasks.json())

    steps_response = httpx.get(
        f"{BASE_URL}/api/tasks/{plan_payload['task_ids'][0]}/steps",
        headers=builder,
        timeout=20.0,
    )
    assert steps_response.status_code == 200
    assert len(steps_response.json()) == 3
