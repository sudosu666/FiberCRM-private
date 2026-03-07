from typing import Any, Optional

import socketio

from ..auth import decode_token
from ..schemas import UserRole

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

class RealtimeManager:
    def __init__(self, server: socketio.AsyncServer):
        self._server = server

    async def broadcast_event(self, event_type: str, payload: Any, room: Optional[str] = None) -> None:
        await self._server.emit(event_type, payload, room=room)


manager = RealtimeManager(sio)


@sio.event
async def connect(sid: str, environ: dict, auth: Optional[dict]) -> None:
    role: Optional[str] = None
    brigade_id: Optional[str] = None
    token = None
    if isinstance(auth, dict):
        role = auth.get('role')
        brigade_id = auth.get('brigade_id')
        token = auth.get('token')
    if token:
        try:
            payload = decode_token(token)
            if payload.role:
                role = payload.role.value
        except Exception:
            pass
    if role == UserRole.Dispatcher.value:
        await sio.enter_room(sid, 'dispatchers')
    elif brigade_id:
        await sio.enter_room(sid, f'brigade_{brigade_id}')
    print(f"User {sid} connected as {role or 'guest'}")


@sio.event
async def disconnect(sid: str) -> None:
    print(f'Disconnected: {sid}')
