from __future__ import annotations

import os

import httpx
import pytest
import socketio


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


def _get_token() -> str:
    response = httpx.post(
        f"{BASE_URL}/token",
        data={"username": "+38000000001", "password": "dispatcher"},
        timeout=20.0,
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_socket_rejects_unauthorized_dispatcher() -> None:
    client = socketio.AsyncClient()
    with pytest.raises(socketio.exceptions.ConnectionError):
        await client.connect(BASE_URL, socketio_path="socket.io", auth={"role": "Dispatcher"})


@pytest.mark.asyncio
async def test_socket_accepts_valid_dispatcher_token() -> None:
    token = _get_token()
    client = socketio.AsyncClient()
    await client.connect(
        BASE_URL,
        socketio_path="socket.io",
        auth={"token": token},
        transports=["websocket"],
    )
    assert client.connected
    await client.disconnect()
