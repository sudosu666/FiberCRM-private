from datetime import datetime
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


@sio.event
async def chat_message(sid: str, data: dict[str, str]) -> None:
    if not isinstance(data, dict):
        return
    brigade_id = data.get('brigade_id')
    payload = {
        'brigade_id': brigade_id,
        'user': data.get('user', 'Бригада'),
        'message': data.get('message', ''),
        'timestamp': data.get('timestamp') or datetime.utcnow().isoformat(),
    }
    await manager.broadcast_event('chat.message', payload, room='dispatchers')
    if brigade_id:
        await manager.broadcast_event('chat.message', payload, room=f'brigade_{brigade_id}')


@sio.event
async def progress_update(sid: str, data: dict[str, str]) -> None:
    if not isinstance(data, dict):
        return
    brigade_id = data.get('brigade_id')
    payload = {
        'brigade_id': brigade_id,
        'step': data.get('step', 'н/д'),
        'timestamp': data.get('timestamp') or datetime.utcnow().isoformat(),
    }
    await manager.broadcast_event('progress.update', payload, room='dispatchers')
    if brigade_id:
        await manager.broadcast_event('progress.update', payload, room=f'brigade_{brigade_id}')
