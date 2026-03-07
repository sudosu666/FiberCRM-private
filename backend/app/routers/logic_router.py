from datetime import datetime
import base64
import binascii
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import Brigade, Task, TaskReport, TaskStatus, User, UserRole
from ..rate_limit import enforce_http_rate_limit
from ..schemas import (
    BrigadeBoardItem,
    TaskAssignRequest,
    TaskQueueItem,
    TimelineHour,
    StockItemRead,
    WarehouseRequestRead,
    NetworkMuffleRead,
    TenderOverview,
    BuildingNetworkRead,
    NetworkOverview,
    TaskReportCreate,
    TaskReportRead,
    FieldMetrics,
)
from ..services.logic import (
    load_brigade_board,
    load_network_topology,
    load_stock_items,
    load_task_queue,
    load_timeline,
    load_warehouse_requests,
    load_tenders,
    load_network_overview,
    load_building_network,
    load_field_metrics,
    refresh_tender_and_building_state,
)
from ..services.realtime import manager as realtime_manager

router = APIRouter(prefix='/api')

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "frontend" / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
REPORT_MAX_UPLOAD_BYTES = 300 * 1024


def _decode_photo_payload(raw_data: str, max_bytes: int) -> bytes:
    header, _, payload = raw_data.partition(',')
    if not payload:
        payload = header
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="photo_data is empty")
    estimated_size = (len(payload) * 3) // 4
    if estimated_size > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="photo_data exceeds max size")
    try:
        decoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail='photo_data should be base64') from exc
    if len(decoded) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="photo_data exceeds max size")
    return decoded


def _build_photo_path(filename: str, payload: bytes) -> str:
    ext = (Path(filename).suffix or ".png").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unsupported file extension")
    target = UPLOAD_DIR / f'{uuid4().hex}{ext}'
    target.write_bytes(payload)
    return f'/static/uploads/{target.name}'


async def _resolve_builder_user(session: AsyncSession, brigade_id: Optional[UUID]) -> Optional[User]:
    builder = None
    if brigade_id:
        brigade = await session.get(Brigade, brigade_id)
        if brigade and brigade.foreman_id:
            builder = await session.get(User, brigade.foreman_id)
        if brigade and not builder:
            builder = (await session.scalars(
                select(User).where(User.role == UserRole.Builder).limit(1)
            )).first()
    if not builder:
        builder = (await session.scalars(
            select(User).where(User.role == UserRole.Builder).limit(1)
        )).first()
    if not builder:
        builder = (await session.scalars(
            select(User).where(User.role == UserRole.Dispatcher).limit(1)
        )).first()
    return builder

@router.get('/tasks', response_model=List[TaskQueueItem])
async def get_tasks(session: AsyncSession = Depends(get_session)) -> List[TaskQueueItem]:
    return await load_task_queue(session)

@router.post('/tasks/{task_id}/assign', response_model=TaskQueueItem)
async def assign_task(
    task_id: UUID,
    body: TaskAssignRequest,
    session: AsyncSession = Depends(get_session),
) -> TaskQueueItem:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    task.brigade_id = body.brigade_id
    task.status = TaskStatus.assigned
    task.assigned_at = datetime.utcnow()
    session.add(task)
    await session.flush()
    await refresh_tender_and_building_state(session, task)
    await session.commit()
    await session.refresh(task)
    queue = await load_task_queue(session)
    await realtime_manager.broadcast_event('task_queue.update', [item.dict() for item in queue])
    brigade_board = await load_brigade_board(session)
    await realtime_manager.broadcast_event('brigade_board.update', [item.dict() for item in brigade_board])
    for item in queue:
        if item.id == str(task.id):
            return item
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build task payload')

@router.get('/brigades', response_model=List[BrigadeBoardItem])
async def get_brigades(session: AsyncSession = Depends(get_session)) -> List[BrigadeBoardItem]:
    return await load_brigade_board(session)

@router.get('/timeline', response_model=List[TimelineHour])
async def get_timeline(session: AsyncSession = Depends(get_session)) -> List[TimelineHour]:
    return await load_timeline(session)

@router.get('/network/topology', response_model=List[NetworkMuffleRead])
async def get_network(session: AsyncSession = Depends(get_session)) -> List[NetworkMuffleRead]:
    return await load_network_topology(session)

@router.get('/network/overview', response_model=NetworkOverview)
async def get_network_overview(session: AsyncSession = Depends(get_session)) -> NetworkOverview:
    return await load_network_overview(session)

@router.get('/buildings/{building_id}/network', response_model=BuildingNetworkRead)
async def get_building_network(building_id: UUID, session: AsyncSession = Depends(get_session)) -> BuildingNetworkRead:
    record = await load_building_network(session, building_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building not found')
    return record


@router.get('/tenders', response_model=List[TenderOverview])
async def get_tenders(session: AsyncSession = Depends(get_session)) -> List[TenderOverview]:
    return await load_tenders(session)

@router.get('/stock', response_model=List[StockItemRead])
async def get_stock(session: AsyncSession = Depends(get_session)) -> List[StockItemRead]:
    return await load_stock_items(session)

@router.get('/warehouse/requests', response_model=List[WarehouseRequestRead])
async def get_requests(session: AsyncSession = Depends(get_session)) -> List[WarehouseRequestRead]:
    return await load_warehouse_requests(session)


@router.get('/field/metrics', response_model=FieldMetrics)
async def get_field_metrics(session: AsyncSession = Depends(get_session)) -> FieldMetrics:
    return await load_field_metrics(session)


@router.post('/tasks/{task_id}/reports', response_model=TaskReportRead, status_code=status.HTTP_201_CREATED)
async def create_task_report(
    request: Request,
    task_id: UUID,
    body: TaskReportCreate,
    session: AsyncSession = Depends(get_session),
) -> TaskReportRead:
    enforce_http_rate_limit(
        request,
        scope="reports.create",
        limit=settings.rate_limit_report_per_minute,
        key_suffix=str(body.brigade_id) if body.brigade_id else None,
    )
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    builder = await _resolve_builder_user(session, body.brigade_id)
    if not builder:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail='No builder user available')
    photo_data = _decode_photo_payload(body.photo_data, max_bytes=REPORT_MAX_UPLOAD_BYTES)
    photo_url = _build_photo_path(body.photo_filename, photo_data)
    brigade_name = body.brigade_name or builder.name
    report = TaskReport(
        task_id=task.id,
        user_id=builder.id,
        photo_url=photo_url,
        comment=body.comment,
        brigade_id=body.brigade_id,
        brigade_name=brigade_name,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    payload = {
        'task_id': str(task.id),
        'brigade_id': str(body.brigade_id) if body.brigade_id else None,
        'brigade_name': report.brigade_name,
        'photo_url': report.photo_url,
        'comment': report.comment,
        'created_at': report.created_at.isoformat(),
    }
    await realtime_manager.broadcast_event('photo.report', payload, room='dispatchers')
    if body.brigade_id:
        await realtime_manager.broadcast_event('photo.report', payload, room=f'brigade_{body.brigade_id}')
    return TaskReportRead(
        id=report.id,
        task_id=report.task_id,
        user_id=report.user_id,
        brigade_id=report.brigade_id,
        brigade_name=report.brigade_name,
        photo_url=report.photo_url,
        comment=report.comment,
        created_at=report.created_at,
    )
