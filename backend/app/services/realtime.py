from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import socketio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import decode_token
from ..config import settings
from ..database import AsyncSessionLocal
from ..models import (
    Brigade,
    BrigadeMember,
    Message,
    Notification,
    Task,
    TaskStatus,
    TaskStep,
    User,
    UserRole as ModelUserRole,
)
from ..schemas import UserRole
from ..rate_limit import limiter

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=settings.cors_origins)
sid_context: dict[str, dict[str, Any]] = {}


def _parse_timestamp(value: Optional[str]) -> datetime:
    if not value:
        return datetime.utcnow()
    if value.endswith('Z'):
        value = value[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.utcnow()


def _to_uuid(value: Optional[str]) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


async def _resolve_dispatcher(session: AsyncSession) -> Optional[User]:
    dispatcher = (await session.scalars(
        select(User).where(User.role == ModelUserRole.Dispatcher).limit(1)
    )).first()
    return dispatcher


async def _resolve_builder(session: AsyncSession, brigade_id: Optional[UUID]) -> Optional[User]:
    if brigade_id:
        brigade = await session.get(Brigade, brigade_id)
        if brigade and brigade.foreman_id:
            builder = await session.get(User, brigade.foreman_id)
            if builder:
                return builder
    builder = (await session.scalars(
        select(User).where(User.role == ModelUserRole.Builder).limit(1)
    )).first()
    if builder:
        return builder
    return await _resolve_dispatcher(session)


class RealtimeManager:
    def __init__(self, server: socketio.AsyncServer):
        self._server = server

    async def broadcast_event(self, event_type: str, payload: Any, room: Optional[str] = None) -> None:
        await self._server.emit(event_type, payload, room=room)


manager = RealtimeManager(sio)


def _sio_key(sid: str, label: str) -> str:
    return f"{sid}:{label}"


@sio.event
async def connect(sid: str, environ: dict, auth: Optional[dict]) -> None:
    client_ip = (environ or {}).get("REMOTE_ADDR", "unknown")
    allowed, _ = limiter.hit(
        "sio.connect",
        str(client_ip),
        settings.rate_limit_realtime_per_minute,
        60,
    )
    if not allowed:
        raise ConnectionRefusedError("Rate limit exceeded")
    if not isinstance(auth, dict):
        raise ConnectionRefusedError("Authentication required")
    token = auth.get("token")
    brigade_id = auth.get("brigade_id")
    if not token:
        raise ConnectionRefusedError("Authentication required")
    try:
        token_data = decode_token(token)
    except Exception as exc:
        raise ConnectionRefusedError("Invalid token") from exc
    if not token_data.phone:
        raise ConnectionRefusedError("Invalid token payload")

    async with AsyncSessionLocal() as session:
        user = (await session.scalars(select(User).where(User.phone == token_data.phone).limit(1))).first()
        if not user:
            raise ConnectionRefusedError("User not found")

        role = token_data.role.value if token_data.role else user.role.value
        if role == UserRole.Dispatcher.value:
            await sio.enter_room(sid, "dispatchers")
        else:
            if not brigade_id:
                raise ConnectionRefusedError("Brigade room requires brigade_id")
            brigade_uuid = _to_uuid(brigade_id)
            if not brigade_uuid:
                raise ConnectionRefusedError("Invalid brigade_id")
            brigade = await session.get(Brigade, brigade_uuid)
            if not brigade:
                raise ConnectionRefusedError("Brigade not found")
            membership_stmt = select(BrigadeMember).where(
                BrigadeMember.brigade_id == brigade.id,
                BrigadeMember.user_id == user.id,
            )
            member = (await session.execute(membership_stmt)).scalars().first()
            if brigade.foreman_id != user.id and not member:
                raise ConnectionRefusedError("Forbidden brigade access")
            await sio.enter_room(sid, f"brigade_{brigade.id}")
            brigade_id = str(brigade.id)

    sid_context[sid] = {
        "user_id": str(user.id),
        "role": role,
        "brigade_id": brigade_id,
    }
    print(f"User {sid} connected as {role}")


@sio.event
async def disconnect(sid: str) -> None:
    sid_context.pop(sid, None)
    print(f'Disconnected: {sid}')


@sio.event
async def chat_message(sid: str, data: dict[str, str]) -> None:
    if not isinstance(data, dict):
        return
    if sid not in sid_context:
        return
    allowed, _ = limiter.hit(
        "sio.chat_message",
        _sio_key(sid, "chat"),
        settings.rate_limit_realtime_per_minute,
        60,
    )
    if not allowed:
        return
    context = sid_context[sid]
    timestamp = _parse_timestamp(data.get('timestamp'))
    brigade_id = context.get("brigade_id") or data.get("brigade_id")
    task_uuid = _to_uuid(data.get('task_id'))
    payload = {
        'brigade_id': brigade_id,
        'brigade_name': data.get('brigade_name'),
        'user': data.get('user'),
        'message': data.get('message', ''),
        'timestamp': timestamp.isoformat(),
        'task_id': str(task_uuid) if task_uuid else None,
    }
    async with AsyncSessionLocal() as session:
        builder = await _resolve_builder(session, _to_uuid(brigade_id))
        dispatcher = await _resolve_dispatcher(session)
        if builder and not payload['brigade_name']:
            payload['brigade_name'] = builder.name
        if not payload['user']:
            payload['user'] = builder.name if builder else 'Бригада'
        task = await session.get(Task, task_uuid) if task_uuid else None
        sender_id = builder.id if builder else dispatcher.id if dispatcher else None
        if task and sender_id:
            message = Message(
                task_id=task.id,
                sender_id=sender_id,
                body=payload['message'],
                photo_url=data.get('photo_url'),
                created_at=timestamp,
            )
            session.add(message)
        await session.commit()
    await manager.broadcast_event('chat.message', payload, room='dispatchers')
    if brigade_id:
        await manager.broadcast_event('chat.message', payload, room=f'brigade_{brigade_id}')


@sio.event
async def progress_update(sid: str, data: dict[str, str]) -> None:
    if not isinstance(data, dict):
        return
    if sid not in sid_context:
        return
    allowed, _ = limiter.hit(
        "sio.progress_update",
        _sio_key(sid, "progress"),
        settings.rate_limit_realtime_per_minute,
        60,
    )
    if not allowed:
        return
    context = sid_context[sid]
    timestamp = _parse_timestamp(data.get('timestamp'))
    brigade_id = context.get("brigade_id") or data.get("brigade_id")
    task_uuid = _to_uuid(data.get('task_id'))
    step_name = data.get('step', 'н/д')
    payload = {
        'brigade_id': brigade_id,
        'brigade_name': data.get('brigade_name'),
        'step': step_name,
        'timestamp': timestamp.isoformat(),
        'task_id': str(task_uuid) if task_uuid else None,
    }
    async with AsyncSessionLocal() as session:
        builder = await _resolve_builder(session, _to_uuid(brigade_id))
        dispatcher = await _resolve_dispatcher(session)
        if builder and not payload['brigade_name']:
            payload['brigade_name'] = builder.name
        task = await session.get(Task, task_uuid) if task_uuid else None
        if task:
            if task.status != TaskStatus.in_progress:
                task.status = TaskStatus.in_progress
            step_stmt = select(TaskStep).where(TaskStep.task_id == task.id, TaskStep.is_done == False).order_by(TaskStep.step_order).limit(1)
            next_step = (await session.execute(step_stmt)).scalars().first()
            if next_step:
                next_step.is_done = True
                next_step.done_at = timestamp
                if builder:
                    next_step.done_by = builder.id
        if dispatcher:
            notification = Notification(
                user_id=dispatcher.id,
                title='progress.update',
                body=f"{payload['brigade_name'] or 'Бригада'} · {step_name}",
                created_at=timestamp,
            )
            session.add(notification)
        await session.commit()
    await manager.broadcast_event('progress.update', payload, room='dispatchers')
    if brigade_id:
        await manager.broadcast_event('progress.update', payload, room=f'brigade_{brigade_id}')
