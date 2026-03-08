from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

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


def test_building_task_and_subscriber_request_comments_and_contacts() -> None:
    dispatcher = _login("+38000000001", "dispatcher")
    connection_dispatcher = _login("+38000000007", "connect-dispatch")

    buildings_response = httpx.get(f"{BASE_URL}/api/buildings", headers=dispatcher, timeout=20.0)
    assert buildings_response.status_code == 200
    building = buildings_response.json()[0]
    building_id = building["building_id"]

    building_comment_body = f"ops-building-{uuid.uuid4().hex[:8]}"
    building_comment = httpx.post(
        f"{BASE_URL}/api/buildings/{building_id}/comments",
        headers=dispatcher,
        json={
            "body": building_comment_body,
            "comment_type": "design_note",
            "role_tags": ["Designer", "Dispatcher"],
        },
        timeout=20.0,
    )
    assert building_comment.status_code == 201
    assert building_comment.json()["body"] == building_comment_body
    assert building_comment.json()["comment_type"] == "design_note"

    building_comments = httpx.get(
        f"{BASE_URL}/api/buildings/{building_id}/comments",
        headers=dispatcher,
        timeout=20.0,
    )
    assert building_comments.status_code == 200
    assert any(item["body"] == building_comment_body for item in building_comments.json())

    tasks_response = httpx.get(f"{BASE_URL}/api/tasks", headers=dispatcher, timeout=20.0)
    assert tasks_response.status_code == 200
    task_id = tasks_response.json()[0]["id"]

    task_comment_body = f"ops-task-{uuid.uuid4().hex[:8]}"
    task_comment = httpx.post(
        f"{BASE_URL}/api/tasks/{task_id}/comments",
        headers=dispatcher,
        json={
            "body": task_comment_body,
            "comment_type": "ops_note",
            "role_tags": ["Dispatcher", "Builder"],
        },
        timeout=20.0,
    )
    assert task_comment.status_code == 201
    assert task_comment.json()["body"] == task_comment_body

    task_contact_phone = f"+38044{uuid.uuid4().int % 1000000:06d}"
    task_contact = httpx.post(
        f"{BASE_URL}/api/tasks/{task_id}/contacts",
        headers=dispatcher,
        json={
            "title": "Concierge",
            "full_name": "Shift Concierge",
            "phone": task_contact_phone,
            "notes": "Access before lunch",
        },
        timeout=20.0,
    )
    assert task_contact.status_code == 201
    assert task_contact.json()["phone"] == task_contact_phone

    task_snapshot = httpx.get(f"{BASE_URL}/api/tasks", headers=dispatcher, timeout=20.0)
    assert task_snapshot.status_code == 200
    task_payload = next(item for item in task_snapshot.json() if item["id"] == task_id)
    assert any(item["body"] == task_comment_body for item in task_payload["comments"])
    assert any(item["phone"] == task_contact_phone for item in task_payload["contacts"])

    create_request = httpx.post(
        f"{BASE_URL}/api/subscriber-requests",
        headers=connection_dispatcher,
        json={
            "building_id": building_id,
            "flat_number": 901,
            "customer_name": "Playwright Customer",
            "phone": f"+38067{uuid.uuid4().int % 1000000:06d}",
            "notes": "Created from API test",
        },
        timeout=20.0,
    )
    assert create_request.status_code == 201
    request_id = create_request.json()["id"]

    request_comment_body = f"subscriber-note-{uuid.uuid4().hex[:8]}"
    request_comment = httpx.post(
        f"{BASE_URL}/api/subscriber-requests/{request_id}/comments",
        headers=connection_dispatcher,
        json={
            "body": request_comment_body,
            "comment_type": "ops_note",
            "role_tags": ["ConnectionDispatcher", "Connector"],
        },
        timeout=20.0,
    )
    assert request_comment.status_code == 201
    assert request_comment.json()["body"] == request_comment_body

    request_contact_phone = f"+38050{uuid.uuid4().int % 1000000:06d}"
    request_contact = httpx.post(
        f"{BASE_URL}/api/subscriber-requests/{request_id}/contacts",
        headers=connection_dispatcher,
        json={
            "title": "OSBB",
            "full_name": "House Office",
            "phone": request_contact_phone,
            "notes": "Call before visit",
        },
        timeout=20.0,
    )
    assert request_contact.status_code == 201
    assert request_contact.json()["phone"] == request_contact_phone

    request_comments = httpx.get(
        f"{BASE_URL}/api/subscriber-requests/{request_id}/comments",
        headers=connection_dispatcher,
        timeout=20.0,
    )
    assert request_comments.status_code == 200
    assert any(item["body"] == request_comment_body for item in request_comments.json())

    request_contacts = httpx.get(
        f"{BASE_URL}/api/subscriber-requests/{request_id}/contacts",
        headers=connection_dispatcher,
        timeout=20.0,
    )
    assert request_contacts.status_code == 200
    assert any(item["phone"] == request_contact_phone for item in request_contacts.json())


def test_connection_dispatch_summary_schedule_and_postpone() -> None:
    connection_dispatcher = _login("+38000000007", "connect-dispatch")

    buildings_response = httpx.get(
        f"{BASE_URL}/api/buildings",
        headers=connection_dispatcher,
        timeout=20.0,
    )
    assert buildings_response.status_code == 200
    building_id = buildings_response.json()[0]["building_id"]

    create_request = httpx.post(
        f"{BASE_URL}/api/subscriber-requests",
        headers=connection_dispatcher,
        json={
            "building_id": building_id,
            "flat_number": 902,
            "customer_name": "Schedule Customer",
            "phone": f"+38093{uuid.uuid4().int % 1000000:06d}",
            "notes": "Needs scheduling",
        },
        timeout=20.0,
    )
    assert create_request.status_code == 201
    request_payload = create_request.json()
    request_id = request_payload["id"]
    assert request_payload["technical_possible"] is True

    workers_response = httpx.get(f"{BASE_URL}/api/field/workers", headers=connection_dispatcher, timeout=20.0)
    assert workers_response.status_code == 200
    technician = workers_response.json()[0]

    scheduled_date = (date.today() + timedelta(days=1)).isoformat()
    schedule_response = httpx.patch(
        f"{BASE_URL}/api/subscriber-requests/{request_id}/schedule",
        headers=connection_dispatcher,
        json={
            "scheduled_date": scheduled_date,
            "arrival_window": "before_lunch",
            "assigned_user_id": technician["id"],
        },
        timeout=20.0,
    )
    assert schedule_response.status_code == 200
    assert schedule_response.json()["status"] == "scheduled"
    assert schedule_response.json()["arrival_window"] == "before_lunch"
    assert schedule_response.json()["assigned_user_id"] == technician["id"]

    postpone_reason = f"awaiting-access-{uuid.uuid4().hex[:6]}"
    postpone_response = httpx.patch(
        f"{BASE_URL}/api/subscriber-requests/{request_id}/postpone",
        headers=connection_dispatcher,
        json={"reason": postpone_reason},
        timeout=20.0,
    )
    assert postpone_response.status_code == 200
    assert postpone_response.json()["status"] == "postponed"
    assert postpone_response.json()["is_postponed"] is True
    assert postpone_response.json()["postponed_reason"] == postpone_reason

    summary_response = httpx.get(
        f"{BASE_URL}/api/subscriber-requests/summary",
        headers=connection_dispatcher,
        timeout=20.0,
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_requests"] >= 1
    assert summary["technical_blocked"] >= 0

    listing_response = httpx.get(
        f"{BASE_URL}/api/subscriber-requests",
        headers=connection_dispatcher,
        timeout=20.0,
    )
    assert listing_response.status_code == 200
    listed_request = next(item for item in listing_response.json() if item["id"] == request_id)
    assert listed_request["assigned_user_id"] == technician["id"]
    assert listed_request["postponed_reason"] == postpone_reason
