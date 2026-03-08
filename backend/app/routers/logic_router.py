from datetime import datetime, timedelta
from math import ceil
import base64
import binascii
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import get_session
from ..models import (
    ArrivalWindow,
    Brigade,
    BrigadeMember,
    Building,
    BuildingNote,
    Fiber,
    FiberStatus,
    InfraStatus,
    Muffle,
    OpsComment,
    OpsContact,
    Panel,
    Port,
    PortStatus,
    RequestStatus,
    StockItem,
    StockTransaction,
    SubscriberRequest,
    SubscriberRequestStatus,
    Task,
    TaskReport,
    TaskStatus,
    TaskStep,
    TaskType,
    Tender,
    TenderStatus,
    User,
    UserRole,
    WorkLog,
    WarehouseRequest,
    WarehouseRequestItem,
)
from ..rate_limit import enforce_http_rate_limit
from ..schemas import (
    BrigadeBoardItem,
    BrigadeUpsert,
    DispatchStatsRead,
    FieldWorkerRead,
    WorkerStatsRead,
    TaskAssignRequest,
    TaskStatusEventRead,
    TaskHoldRequest,
    TaskPostponeRequest,
    TaskQueueItem,
    TaskStepRead,
    TaskStepCompleteRead,
    TimelineHour,
    StockItemRead,
    StockAdjustRequest,
    StockTransactionRead,
    SubscriberDispatcherSummary,
    SubscriberRequestCreate,
    SubscriberRequestPostpone,
    SubscriberRequestRead,
    SubscriberRequestSchedule,
    WarehouseRequestRead,
    WarehouseRequestFulfill,
    WarehouseRequestCreate,
    NetworkMuffleRead,
    TenderOverview,
    TenderCreate,
    TenderStatusUpdate,
    TenderDashboardRead,
    TenderCompleteRead,
    BuildingNetworkRead,
    BuildingNoteCreate,
    BuildingNoteRead,
    BuildingSummaryRead,
    NetworkOverview,
    BuildingCalculateRead,
    MuffleCapacityRead,
    MuffleCapacityFiberRead,
    OpsCommentCreate,
    OpsCommentRead,
    OpsContactCreate,
    OpsContactRead,
    InfrastructureBuildingRead,
    InfrastructurePanelRead,
    InfrastructurePortRead,
    TaskReportCreate,
    TaskReportRead,
    FieldMetrics,
    NetworkPlanCreate,
    NetworkPlanRead,
    WorkSummaryRead,
)
from .auth_helpers import require_roles
from .auth_helpers import user_has_role
from ..services.logic import (
    load_brigade_board,
    load_dispatch_stats,
    load_field_workers,
    load_network_topology,
    load_stock_items,
    load_stock_transactions,
    load_task_queue,
    load_timeline,
    load_warehouse_requests,
    load_tenders,
    load_network_overview,
    load_building_network,
    load_building_summaries,
    load_field_metrics,
    load_subscriber_dispatch_summary,
    load_subscriber_requests,
    load_task_work_summary,
    refresh_tender_and_building_state,
    load_worker_stats,
)
from ..services.realtime import manager as realtime_manager

router = APIRouter(prefix='/api')

dispatcher_only = Depends(require_roles(UserRole.Dispatcher))
designer_only = Depends(require_roles(UserRole.Designer))
warehouse_only = Depends(require_roles(UserRole.Warehouse))
warehouse_or_designer = Depends(require_roles(UserRole.Warehouse, UserRole.Designer))
field_roles = Depends(require_roles(UserRole.Builder, UserRole.Welder, UserRole.Connector))
ops_roles = Depends(require_roles(UserRole.Dispatcher, UserRole.Builder, UserRole.Welder, UserRole.Connector))
connection_dispatcher_only = Depends(require_roles(UserRole.ConnectionDispatcher))
subscriber_dispatch_roles = Depends(require_roles(UserRole.Dispatcher, UserRole.ConnectionDispatcher))

UPLOAD_DIR = Path(__file__).resolve().parents[3] / "frontend" / "app" / "static" / "uploads"
if not UPLOAD_DIR.exists():
    UPLOAD_DIR = Path(__file__).resolve().parents[1] / "frontend" / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
REPORT_MAX_UPLOAD_BYTES = 300 * 1024


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


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


def _role_tag_values(tags: list[UserRole]) -> str | None:
    values = ",".join(sorted({tag.value for tag in tags})) if tags else ""
    return values or None


async def _resolve_builder_user(session: AsyncSession, brigade_id: Optional[UUID]) -> Optional[User]:
    builder = None
    if brigade_id:
        brigade = await session.get(Brigade, brigade_id)
        if brigade and brigade.foreman_id:
            builder = await session.get(User, brigade.foreman_id)
        if brigade and not builder:
            users = (await session.scalars(select(User))).all()
            builder = next((user for user in users if user_has_role(user, UserRole.Builder)), None)
    if not builder:
        users = (await session.scalars(select(User))).all()
        builder = next((user for user in users if user_has_role(user, UserRole.Builder)), None)
    if not builder:
        users = (await session.scalars(select(User))).all()
        builder = next((user for user in users if user_has_role(user, UserRole.Dispatcher)), None)
    return builder

@router.get('/tasks', response_model=List[TaskQueueItem])
async def get_tasks(
    session: AsyncSession = Depends(get_session),
    current_user: User = ops_roles,
) -> List[TaskQueueItem]:
    queue = await load_task_queue(session)
    if user_has_role(current_user, UserRole.Dispatcher):
        return queue
    brigade_ids = set((await session.scalars(
        select(BrigadeMember.brigade_id).where(BrigadeMember.user_id == current_user.id)
    )).all())
    led_brigades = set((await session.scalars(
        select(Brigade.id).where(Brigade.foreman_id == current_user.id)
    )).all())
    brigade_ids.update(led_brigades)
    if not brigade_ids:
        return []
    return [item for item in queue if item.brigade_id and UUID(str(item.brigade_id)) in brigade_ids]


@router.get('/tasks/{task_id}/steps', response_model=List[TaskStepRead])
async def get_task_steps(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> List[TaskStepRead]:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    steps = (await session.scalars(
        select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.step_order)
    )).all()
    return [
        TaskStepRead(
            id=step.id,
            task_id=step.task_id,
            step_order=step.step_order,
            title=step.title,
            hint=step.hint,
            is_done=step.is_done,
            done_at=step.done_at,
        )
        for step in steps
    ]


@router.patch('/tasks/{task_id}/steps/{step_id}/complete', response_model=TaskStepCompleteRead)
async def complete_task_step(
    task_id: UUID,
    step_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = field_roles,
) -> TaskStepCompleteRead:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    step = await session.get(TaskStep, step_id)
    if not step or step.task_id != task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Step not found')
    step.is_done = True
    step.done_at = datetime.utcnow()
    step.done_by = current_user.id
    task.status = TaskStatus.in_progress
    session.add(step)
    session.add(task)
    session.add(WorkLog(
        user_id=current_user.id,
        task_id=task.id,
        event_type='task.step.completed',
        description=step.title,
        quantity=1.0,
        unit='step',
        event_at=step.done_at,
    ))
    await session.flush()
    await refresh_tender_and_building_state(session, task)
    await session.commit()
    payload = {
        'event_type': 'task.step.completed',
        'task_id': str(task.id),
        'step': step.title,
        'timestamp': step.done_at.isoformat() if step.done_at else datetime.utcnow().isoformat(),
        'event_at': step.done_at.isoformat() if step.done_at else _now_iso(),
        'recorded_at': _now_iso(),
    }
    await realtime_manager.broadcast_event('progress.update', payload, room='dispatchers')
    return TaskStepCompleteRead(
        task_id=task.id,
        step_id=step.id,
        is_done=step.is_done,
        done_at=step.done_at,
        event_at=step.done_at,
    )


@router.patch('/tasks/{task_id}/start', response_model=TaskStatusEventRead)
async def start_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = field_roles,
) -> TaskStatusEventRead:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    event_at = datetime.utcnow()
    task.status = TaskStatus.in_progress
    task.started_at = task.started_at or event_at
    task.hold_reason = None
    task.postponed_reason = None
    task.postponed_at = None
    task.is_critical = False
    session.add(task)
    session.add(WorkLog(
        user_id=current_user.id,
        task_id=task.id,
        event_type='task.started',
        description='Task started by field worker',
        quantity=1.0,
        unit='task',
        event_at=event_at,
    ))
    await session.flush()
    await refresh_tender_and_building_state(session, task)
    await session.commit()
    await realtime_manager.broadcast_event('task.status', {
        'event_type': 'task.started',
        'task_id': str(task.id),
        'status': task.status.value,
        'event_at': event_at.isoformat(),
        'recorded_at': _now_iso(),
        'is_critical': task.is_critical,
        'hold_reason': task.hold_reason,
    }, room='dispatchers')
    return TaskStatusEventRead(task_id=task.id, status=task.status, event_at=event_at, hold_reason=task.hold_reason, is_critical=task.is_critical)


@router.patch('/tasks/{task_id}/finish', response_model=TaskStatusEventRead)
async def finish_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = field_roles,
) -> TaskStatusEventRead:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    event_at = datetime.utcnow()
    task.status = TaskStatus.completed
    task.ended_at = event_at
    task.completed_at = event_at
    task.hold_reason = None
    task.postponed_reason = None
    task.postponed_at = None
    task.is_critical = False
    session.add(task)
    session.add(WorkLog(
        user_id=current_user.id,
        task_id=task.id,
        event_type='task.finished',
        description='Task finished by field worker',
        quantity=1.0,
        unit='task',
        event_at=event_at,
    ))
    await session.flush()
    await refresh_tender_and_building_state(session, task)
    await session.commit()
    await realtime_manager.broadcast_event('task.status', {
        'event_type': 'task.finished',
        'task_id': str(task.id),
        'status': task.status.value,
        'event_at': event_at.isoformat(),
        'recorded_at': _now_iso(),
        'is_critical': task.is_critical,
        'hold_reason': task.hold_reason,
    }, room='dispatchers')
    return TaskStatusEventRead(task_id=task.id, status=task.status, event_at=event_at, hold_reason=task.hold_reason, is_critical=task.is_critical)


@router.patch('/tasks/{task_id}/hold', response_model=TaskStatusEventRead)
async def hold_task(
    task_id: UUID,
    body: TaskHoldRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = field_roles,
) -> TaskStatusEventRead:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    event_at = datetime.utcnow()
    task.status = TaskStatus.on_hold
    task.hold_reason = body.reason
    task.is_critical = body.is_critical
    session.add(task)
    session.add(WorkLog(
        user_id=current_user.id,
        task_id=task.id,
        event_type='task.on_hold',
        description=body.reason,
        quantity=1.0,
        unit='incident',
        event_at=event_at,
    ))
    await session.flush()
    await refresh_tender_and_building_state(session, task)
    await session.commit()
    await realtime_manager.broadcast_event('task.status', {
        'event_type': 'task.on_hold',
        'task_id': str(task.id),
        'status': task.status.value,
        'event_at': event_at.isoformat(),
        'recorded_at': _now_iso(),
        'is_critical': task.is_critical,
        'hold_reason': task.hold_reason,
    }, room='dispatchers')
    return TaskStatusEventRead(task_id=task.id, status=task.status, event_at=event_at, hold_reason=task.hold_reason, is_critical=task.is_critical)


@router.patch('/tasks/{task_id}/postpone', response_model=TaskStatusEventRead)
async def postpone_task(
    task_id: UUID,
    body: TaskPostponeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = field_roles,
) -> TaskStatusEventRead:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    event_at = datetime.utcnow()
    task.status = TaskStatus.on_hold
    task.hold_reason = f'Перенос: {body.reason}'
    task.is_critical = False
    session.add(task)
    session.add(OpsComment(
        task_id=task.id,
        author_id=current_user.id,
        comment_type='postpone',
        body=body.reason,
    ))
    session.add(WorkLog(
        user_id=current_user.id,
        task_id=task.id,
        event_type='task.postponed',
        description=body.reason,
        quantity=1.0,
        unit='incident',
        event_at=event_at,
    ))
    await session.flush()
    await refresh_tender_and_building_state(session, task)
    await session.commit()
    await realtime_manager.broadcast_event('task.status', {
        'event_type': 'task.postponed',
        'task_id': str(task.id),
        'status': task.status.value,
        'event_at': event_at.isoformat(),
        'recorded_at': _now_iso(),
        'is_critical': task.is_critical,
        'hold_reason': task.hold_reason,
        'postponed_reason': body.reason,
        'postponed_at': event_at.isoformat(),
    }, room='dispatchers')
    return TaskStatusEventRead(task_id=task.id, status=task.status, event_at=event_at, hold_reason=task.hold_reason, is_critical=task.is_critical)

@router.post('/tasks/{task_id}/assign', response_model=TaskQueueItem)
async def assign_task(
    task_id: UUID,
    body: TaskAssignRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = dispatcher_only,
) -> TaskQueueItem:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    task.brigade_id = body.brigade_id
    task.status = TaskStatus.assigned
    task.assigned_at = datetime.utcnow()
    session.add(task)
    session.add(WorkLog(
        user_id=current_user.id,
        task_id=task.id,
        event_type='task.assigned',
        description=f'Assigned to brigade {body.brigade_id}',
        quantity=1.0,
        unit='assignment',
        event_at=task.assigned_at,
    ))
    await session.flush()
    await refresh_tender_and_building_state(session, task)
    await session.commit()
    await session.refresh(task)
    queue = await load_task_queue(session)
    event_at = task.assigned_at.isoformat() if task.assigned_at else _now_iso()
    await realtime_manager.broadcast_event('task_queue.update', {
        'event_type': 'task_queue.update',
        'event_at': event_at,
        'recorded_at': _now_iso(),
        'items': [item.dict() for item in queue],
    })
    brigade_board = await load_brigade_board(session)
    await realtime_manager.broadcast_event('brigade_board.update', {
        'event_type': 'brigade_board.update',
        'event_at': event_at,
        'recorded_at': _now_iso(),
        'items': [item.dict() for item in brigade_board],
    })
    for item in queue:
        if item.id == task.id:
            return item
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build task payload')

@router.get('/brigades', response_model=List[BrigadeBoardItem])
async def get_brigades(
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_only,
) -> List[BrigadeBoardItem]:
    return await load_brigade_board(session)


@router.get('/field/workers', response_model=List[FieldWorkerRead])
async def get_field_workers(
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> List[FieldWorkerRead]:
    return await load_field_workers(session)


@router.post('/brigades', response_model=BrigadeBoardItem, status_code=status.HTTP_201_CREATED)
async def create_brigade(
    body: BrigadeUpsert,
    session: AsyncSession = Depends(get_session),
    current_user: User = dispatcher_only,
) -> BrigadeBoardItem:
    brigade = Brigade(
        name=body.name,
        type=body.type,
        foreman_id=body.foreman_id,
        is_active=body.is_active,
    )
    session.add(brigade)
    await session.flush()
    for member_id in sorted(set(body.member_ids)):
        session.add(BrigadeMember(brigade_id=brigade.id, user_id=member_id))
    session.add(WorkLog(
        user_id=current_user.id,
        event_type='brigade.created',
        description=f'{body.name} ({body.type.value})',
        quantity=float(len(set(body.member_ids))),
        unit='member',
        event_at=datetime.utcnow(),
    ))
    await session.commit()
    board = await load_brigade_board(session)
    await realtime_manager.broadcast_event('brigade_board.update', {
        'event_type': 'brigade_board.update',
        'event_at': _now_iso(),
        'recorded_at': _now_iso(),
        'items': [item.model_dump(mode='json') for item in board],
    })
    for item in board:
        if item.id == brigade.id:
            return item
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build brigade payload')


@router.patch('/brigades/{brigade_id}', response_model=BrigadeBoardItem)
async def update_brigade(
    brigade_id: UUID,
    body: BrigadeUpsert,
    session: AsyncSession = Depends(get_session),
    current_user: User = dispatcher_only,
) -> BrigadeBoardItem:
    brigade = await session.get(Brigade, brigade_id)
    if not brigade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Brigade not found')
    brigade.name = body.name
    brigade.type = body.type
    brigade.foreman_id = body.foreman_id
    brigade.is_active = body.is_active
    session.add(brigade)
    existing = (await session.scalars(select(BrigadeMember).where(BrigadeMember.brigade_id == brigade.id))).all()
    for member in existing:
        await session.delete(member)
    await session.flush()
    for member_id in sorted(set(body.member_ids)):
        session.add(BrigadeMember(brigade_id=brigade.id, user_id=member_id))
    session.add(WorkLog(
        user_id=current_user.id,
        event_type='brigade.updated',
        description=f'{body.name} ({body.type.value})',
        quantity=float(len(set(body.member_ids))),
        unit='member',
        event_at=datetime.utcnow(),
    ))
    await session.commit()
    board = await load_brigade_board(session)
    await realtime_manager.broadcast_event('brigade_board.update', {
        'event_type': 'brigade_board.update',
        'event_at': _now_iso(),
        'recorded_at': _now_iso(),
        'items': [item.model_dump(mode='json') for item in board],
    })
    for item in board:
        if item.id == brigade.id:
            return item
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build brigade payload')

@router.get('/timeline', response_model=List[TimelineHour])
async def get_timeline(
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_only,
) -> List[TimelineHour]:
    return await load_timeline(session)


@router.get('/dispatch/stats', response_model=DispatchStatsRead)
async def get_dispatch_stats(
    status: str | None = None,
    task_type: str | None = None,
    brigade_id: UUID | None = None,
    city: str | None = None,
    critical_only: bool = False,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_only,
) -> DispatchStatsRead:
    return await load_dispatch_stats(
        session,
        status=status,
        task_type=task_type,
        brigade_id=brigade_id,
        city=city,
        critical_only=critical_only,
        search=search,
    )


@router.get('/dispatch/workers/stats', response_model=List[WorkerStatsRead])
async def get_dispatch_worker_stats(
    role: str | None = None,
    brigade_id: UUID | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_only,
) -> List[WorkerStatsRead]:
    return await load_worker_stats(
        session,
        role=role,
        brigade_id=brigade_id,
        search=search,
    )

@router.get('/network/topology', response_model=List[NetworkMuffleRead])
async def get_network(
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> List[NetworkMuffleRead]:
    return await load_network_topology(session)

@router.get('/network/overview', response_model=NetworkOverview)
async def get_network_overview(
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> NetworkOverview:
    return await load_network_overview(session)

@router.get('/buildings/{building_id}/network', response_model=BuildingNetworkRead)
async def get_building_network(
    building_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> BuildingNetworkRead:
    record = await load_building_network(session, building_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building not found')
    return record


@router.get('/buildings', response_model=List[BuildingSummaryRead])
async def get_buildings(
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> List[BuildingSummaryRead]:
    return await load_building_summaries(session)


@router.get('/subscriber-requests', response_model=List[SubscriberRequestRead])
async def get_subscriber_requests(
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> List[SubscriberRequestRead]:
    return await load_subscriber_requests(session)


@router.get('/subscriber-requests/summary', response_model=SubscriberDispatcherSummary)
async def get_subscriber_requests_summary(
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> SubscriberDispatcherSummary:
    return await load_subscriber_dispatch_summary(session)


@router.post('/subscriber-requests', response_model=SubscriberRequestRead, status_code=status.HTTP_201_CREATED)
async def create_subscriber_request(
    body: SubscriberRequestCreate,
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> SubscriberRequestRead:
    building = await session.get(Building, body.building_id)
    if not building:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building not found')
    request = SubscriberRequest(
        building_id=body.building_id,
        flat_number=body.flat_number,
        customer_name=body.customer_name,
        phone=body.phone,
        notes=body.notes,
        status=SubscriberRequestStatus.new,
        deadline_at=datetime.utcnow() + timedelta(days=14),
    )
    session.add(request)
    await session.commit()
    request = (await session.scalars(
        select(SubscriberRequest)
        .options(
            selectinload(SubscriberRequest.building).selectinload(Building.panels).selectinload(Panel.ports),
            selectinload(SubscriberRequest.assigned_user),
            selectinload(SubscriberRequest.contacts),
            selectinload(SubscriberRequest.comments).selectinload(OpsComment.author),
        )
        .where(SubscriberRequest.id == request.id)
    )).one()
    from ..services.logic import serialize_subscriber_request
    return serialize_subscriber_request(request)


@router.patch('/subscriber-requests/{request_id}/schedule', response_model=SubscriberRequestRead)
async def schedule_subscriber_request(
    request_id: UUID,
    body: SubscriberRequestSchedule,
    session: AsyncSession = Depends(get_session),
    _: User = connection_dispatcher_only,
) -> SubscriberRequestRead:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    assigned_user = await session.get(User, body.assigned_user_id)
    if not assigned_user or not any(user_has_role(assigned_user, role) for role in (UserRole.Builder, UserRole.Welder, UserRole.Connector)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Assigned user should be a field technician')
    request.scheduled_date = body.scheduled_date
    request.arrival_window = ArrivalWindow(body.arrival_window.value)
    request.assigned_user_id = body.assigned_user_id
    request.status = SubscriberRequestStatus.scheduled
    session.add(request)
    await session.commit()
    request = (await session.scalars(
        select(SubscriberRequest)
        .options(
            selectinload(SubscriberRequest.building).selectinload(Building.panels).selectinload(Panel.ports),
            selectinload(SubscriberRequest.assigned_user),
            selectinload(SubscriberRequest.contacts),
            selectinload(SubscriberRequest.comments).selectinload(OpsComment.author),
        )
        .where(SubscriberRequest.id == request_id)
    )).one()
    from ..services.logic import serialize_subscriber_request
    return serialize_subscriber_request(request)


@router.patch('/subscriber-requests/{request_id}/postpone', response_model=SubscriberRequestRead)
async def postpone_subscriber_request(
    request_id: UUID,
    body: SubscriberRequestPostpone,
    session: AsyncSession = Depends(get_session),
    _: User = connection_dispatcher_only,
) -> SubscriberRequestRead:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    request.status = SubscriberRequestStatus.postponed
    session.add(request)
    session.add(OpsComment(
        subscriber_request_id=request.id,
        comment_type='postpone',
        body=body.reason,
    ))
    await session.commit()
    request = (await session.scalars(
        select(SubscriberRequest)
        .options(
            selectinload(SubscriberRequest.building).selectinload(Building.panels).selectinload(Panel.ports),
            selectinload(SubscriberRequest.assigned_user),
            selectinload(SubscriberRequest.contacts),
            selectinload(SubscriberRequest.comments).selectinload(OpsComment.author),
        )
        .where(SubscriberRequest.id == request_id)
    )).one()
    from ..services.logic import serialize_subscriber_request
    return serialize_subscriber_request(request)


@router.get('/subscriber-requests/{request_id}/comments', response_model=List[OpsCommentRead])
async def get_subscriber_request_comments(
    request_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> List[OpsCommentRead]:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    comments = (await session.scalars(
        select(OpsComment)
        .options(selectinload(OpsComment.author))
        .where(OpsComment.subscriber_request_id == request_id)
        .order_by(OpsComment.created_at.desc())
    )).all()
    from ..services.logic import serialize_ops_comment
    return [serialize_ops_comment(comment) for comment in comments]


@router.post('/subscriber-requests/{request_id}/comments', response_model=OpsCommentRead, status_code=status.HTTP_201_CREATED)
async def create_subscriber_request_comment(
    request_id: UUID,
    body: OpsCommentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = subscriber_dispatch_roles,
) -> OpsCommentRead:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    comment = OpsComment(
        subscriber_request_id=request_id,
        author_id=current_user.id,
        comment_type=body.comment_type,
        body=body.body,
        role_tags=_role_tag_values(body.role_tags),
    )
    session.add(comment)
    await session.commit()
    comment = (await session.scalars(
        select(OpsComment).options(selectinload(OpsComment.author)).where(OpsComment.id == comment.id)
    )).one()
    from ..services.logic import serialize_ops_comment
    return serialize_ops_comment(comment)


@router.get('/subscriber-requests/{request_id}/contacts', response_model=List[OpsContactRead])
async def get_subscriber_request_contacts(
    request_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> List[OpsContactRead]:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    contacts = (await session.scalars(
        select(OpsContact).where(OpsContact.subscriber_request_id == request_id).order_by(OpsContact.created_at.desc())
    )).all()
    from ..services.logic import serialize_ops_contact
    return [serialize_ops_contact(contact) for contact in contacts]


@router.post('/subscriber-requests/{request_id}/contacts', response_model=OpsContactRead, status_code=status.HTTP_201_CREATED)
async def create_subscriber_request_contact(
    request_id: UUID,
    body: OpsContactCreate,
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> OpsContactRead:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    contact = OpsContact(
        subscriber_request_id=request_id,
        title=body.title,
        full_name=body.full_name,
        phone=body.phone,
        notes=body.notes,
    )
    session.add(contact)
    await session.commit()
    from ..services.logic import serialize_ops_contact
    return serialize_ops_contact(contact)


@router.get('/buildings/{building_id}/notes', response_model=List[BuildingNoteRead])
async def get_building_notes(
    building_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> List[BuildingNoteRead]:
    building = await session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building not found')
    notes = (await session.scalars(
        select(BuildingNote)
        .options(selectinload(BuildingNote.author))
        .where(BuildingNote.building_id == building_id)
        .order_by(BuildingNote.created_at.desc())
    )).all()
    from ..services.logic import serialize_building_note
    return [serialize_building_note(note) for note in notes]


@router.post('/buildings/{building_id}/notes', response_model=BuildingNoteRead, status_code=status.HTTP_201_CREATED)
async def create_building_note(
    building_id: UUID,
    body: BuildingNoteCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = ops_roles,
) -> BuildingNoteRead:
    building = await session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building not found')
    note = BuildingNote(
        building_id=building_id,
        author_id=current_user.id,
        body=body.body,
        role_tags=",".join(sorted({role.value for role in body.role_tags})) or None,
    )
    session.add(note)
    await session.commit()
    note = (await session.scalars(
        select(BuildingNote)
        .options(selectinload(BuildingNote.author))
        .where(BuildingNote.id == note.id)
    )).one()
    from ..services.logic import serialize_building_note
    return serialize_building_note(note)


@router.get('/buildings/{building_id}/comments', response_model=List[OpsCommentRead])
async def get_building_comments(
    building_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> List[OpsCommentRead]:
    building = await session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building not found')
    comments = (await session.scalars(
        select(OpsComment)
        .options(selectinload(OpsComment.author))
        .where(OpsComment.building_id == building_id)
        .order_by(OpsComment.created_at.desc())
    )).all()
    from ..services.logic import serialize_ops_comment
    return [serialize_ops_comment(comment) for comment in comments]


@router.post('/buildings/{building_id}/comments', response_model=OpsCommentRead, status_code=status.HTTP_201_CREATED)
async def create_building_comment(
    building_id: UUID,
    body: OpsCommentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = ops_roles,
) -> OpsCommentRead:
    building = await session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building not found')
    comment = OpsComment(
        building_id=building_id,
        author_id=current_user.id,
        comment_type=body.comment_type,
        body=body.body,
        role_tags=_role_tag_values(body.role_tags),
    )
    session.add(comment)
    await session.commit()
    comment = (await session.scalars(
        select(OpsComment).options(selectinload(OpsComment.author)).where(OpsComment.id == comment.id)
    )).one()
    from ..services.logic import serialize_ops_comment
    return serialize_ops_comment(comment)


@router.post('/network/buildings/{building_id}/calculate', response_model=BuildingCalculateRead)
async def calculate_building_network(
    building_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> BuildingCalculateRead:
    building = await session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building not found')
    panel_every = building.panel_every_n_floors or 5
    panels = building.entrances_count * ceil(building.floors_count / panel_every)
    floor_height = building.floor_height_m or 2.8
    reserve = building.cable_reserve_pct or 15
    distance = building.distance_from_muffle_m or 0.0
    total_cable = (building.entrances_count * building.floors_count * floor_height + distance) * (1 + reserve / 100)
    metrics = await load_building_network(session, building_id)
    if not metrics:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building metrics unavailable')
    potential_clients = building.entrances_count * building.floors_count * building.flats_per_floor
    return BuildingCalculateRead(
        building_id=building.id,
        metrics=metrics.metrics,
        patches_needed=panels * 8,
        muffles_needed=1,
        potential_clients=potential_clients,
    )


@router.get('/network/muffles/{muffle_id}/capacity', response_model=MuffleCapacityRead)
async def get_muffle_capacity(
    muffle_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> MuffleCapacityRead:
    muffle = await session.get(Muffle, muffle_id)
    if not muffle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Muffle not found')
    fibers = (await session.scalars(select(Fiber).where(Fiber.muffle_id == muffle.id))).all()
    result_fibers: list[MuffleCapacityFiberRead] = []
    warning = None
    for fiber in fibers:
        used_ports = 32 if fiber.status == FiberStatus.busy else 16 if fiber.status == FiberStatus.reserved else 0
        clients = used_ports
        available = max(0, 32 - used_ports)
        load_pct = round((used_ports / 32) * 100, 2)
        if load_pct > 85:
            warning = 'Fiber load exceeds 85%; consider extra muffle capacity'
        result_fibers.append(MuffleCapacityFiberRead(
            fiber_num=fiber.fiber_number,
            used_ports=used_ports,
            clients=clients,
            available_ports=available,
            load_pct=load_pct,
        ))
    return MuffleCapacityRead(muffle_id=muffle.id, warning=warning, fibers=result_fibers)


@router.post('/network/plan', response_model=NetworkPlanRead, status_code=status.HTTP_201_CREATED)
async def create_network_plan(
    body: NetworkPlanCreate,
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> NetworkPlanRead:
    tender: Optional[Tender] = None
    if body.tender_id:
        tender = await session.get(Tender, body.tender_id)
    if not tender:
        tender = (await session.scalars(select(Tender).limit(1))).first()
    if not tender:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Tender not found')

    building = Building(
        tender_id=tender.id,
        address=body.address,
        city=body.city or tender.city,
        servicing_org_name=body.servicing_org_name,
        servicing_org_phone=body.servicing_org_phone,
        entrances_count=body.entrances_count,
        floors_count=body.floors_count,
        flats_per_floor=body.flats_per_floor,
        floor_height_m=body.floor_height_m,
        panel_every_n_floors=body.panel_every_n_floors,
        distance_from_muffle_m=body.distance_from_muffle_m,
        cable_reserve_pct=body.cable_reserve_pct,
    )
    session.add(building)
    await session.flush()

    brigades = (await session.scalars(select(Brigade))).all()
    brigade_map = {brigade.type: brigade for brigade in brigades}
    task_specs = [
        (TaskType.construction, 'Будівельний етап: прокладка кабелю та монтаж щитків'),
        (TaskType.welding, 'Зварювальний етап: муфти, розшивка щитків'),
        (TaskType.connection, 'Підключення клієнтів та активація портів'),
    ]
    created_tasks: list[Task] = []
    for task_type, description in task_specs:
        task = Task(
            type=task_type,
            status=TaskStatus.pending,
            priority=0,
            building_id=building.id,
            brigade_id=brigade_map.get(task_type).id if brigade_map.get(task_type) else None,
            description=description,
            estimated_hours=4.0 if task_type == TaskType.construction else 3.0,
        )
        session.add(task)
        created_tasks.append(task)
    await session.flush()

    construction_task = created_tasks[0]
    for step_order, (title, hint) in enumerate([
        ('Отримати матеріали на складі', 'Кабель, муфта, патч-корди'),
        ('Прокласти кабельну трасу', f'Відстань від муфти: {body.distance_from_muffle_m}м'),
        ('Монтувати щитки по поверхах', f'Кожні {body.panel_every_n_floors} поверхів'),
    ], start=1):
        session.add(TaskStep(task_id=construction_task.id, step_order=step_order, title=title, hint=hint))

    reserved_fibers: list[int] = []
    if body.muffle_id and body.selected_fibers:
        target_fibers = (await session.scalars(
            select(Fiber).where(
                Fiber.muffle_id == body.muffle_id,
                Fiber.fiber_number.in_(body.selected_fibers),
            )
        )).all()
        by_number = {fiber.fiber_number: fiber for fiber in target_fibers}
        for fiber_number in body.selected_fibers:
            fiber = by_number.get(fiber_number)
            if fiber and fiber.status == FiberStatus.free:
                fiber.status = FiberStatus.reserved
                session.add(fiber)
                reserved_fibers.append(fiber_number)

    dispatcher = (await session.scalars(
        select(User).where(User.role == UserRole.Dispatcher).limit(1)
    )).first()

    warehouse_request_id: Optional[UUID] = None
    if dispatcher:
        panel_count = body.entrances_count * ceil(body.floors_count / body.panel_every_n_floors)
        inner = body.entrances_count * body.floors_count * body.floor_height_m
        outer = body.distance_from_muffle_m
        cable_need = ceil((inner + outer) * (1 + body.cable_reserve_pct / 100))

        request = WarehouseRequest(
            requested_by=dispatcher.id,
            task_id=construction_task.id,
            building_id=building.id,
            status=RequestStatus.pending,
            notes='Автоматична заявка з модуля проектувальника',
        )
        session.add(request)
        await session.flush()
        warehouse_request_id = request.id

        stock_items = (await session.scalars(select(StockItem))).all()
        cable_item = next((item for item in stock_items if 'кабель' in item.name.lower()), None)
        muffle_item = next((item for item in stock_items if 'муфта' in item.name.lower()), None)
        panel_item = next((item for item in stock_items if 'щит' in item.name.lower()), None)

        req_items: list[WarehouseRequestItem] = []
        if cable_item:
            req_items.append(WarehouseRequestItem(request_id=request.id, stock_item_id=cable_item.id, planned_qty=float(cable_need)))
        if muffle_item:
            req_items.append(WarehouseRequestItem(request_id=request.id, stock_item_id=muffle_item.id, planned_qty=1.0))
        if panel_item:
            req_items.append(WarehouseRequestItem(request_id=request.id, stock_item_id=panel_item.id, planned_qty=float(panel_count)))
        session.add_all(req_items)

    await session.commit()

    return NetworkPlanRead(
        building_id=building.id,
        task_ids=[task.id for task in created_tasks],
        warehouse_request_id=warehouse_request_id,
        reserved_fibers=reserved_fibers,
    )


@router.get('/network/infrastructure', response_model=List[InfrastructureBuildingRead])
async def get_infrastructure_registry(
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_only,
) -> List[InfrastructureBuildingRead]:
    buildings = (await session.scalars(
        select(Building).where(Building.infrastructure_status == InfraStatus.completed)
    )).all()
    payload: list[InfrastructureBuildingRead] = []
    for building in buildings:
        panels = (await session.scalars(
            select(Panel).options(selectinload(Panel.ports)).where(Panel.building_id == building.id)
        )).all()
        metrics = calculate_building_metrics(building)
        panel_items: list[InfrastructurePanelRead] = []
        connected_lines = 0
        reserved_lines = 0
        for panel in panels:
            ports = [
                InfrastructurePortRead(
                    panel_id=panel.id,
                    port_id=port.id,
                    port_number=port.port_number,
                    status=port.status.value if isinstance(port.status, PortStatus) else str(port.status),
                )
                for port in panel.ports
            ]
            connected_lines += sum(1 for port in panel.ports if port.status == PortStatus.active)
            reserved_lines += sum(1 for port in panel.ports if port.status == PortStatus.reserved)
            panel_items.append(InfrastructurePanelRead(
                panel_id=panel.id,
                entrance_num=panel.entrance_num,
                floor_num=panel.floor_num,
                label=panel.label,
                ports=ports,
            ))
        notes = (await session.scalars(
            select(BuildingNote).options(selectinload(BuildingNote.author)).where(BuildingNote.building_id == building.id).order_by(BuildingNote.created_at.desc())
        )).all()
        from ..services.logic import serialize_building_note
        payload.append(InfrastructureBuildingRead(
            building_id=building.id,
            address=building.address,
            city=building.city,
            infrastructure_status=building.infrastructure_status.value if isinstance(building.infrastructure_status, InfraStatus) else str(building.infrastructure_status),
            connected_lines=connected_lines,
            reserved_lines=reserved_lines,
            unclaimed_lines=max(0, metrics.total_flats - connected_lines - reserved_lines),
            panels=panel_items,
            notes=[serialize_building_note(note) for note in notes],
        ))
    return payload


@router.get('/tenders', response_model=List[TenderOverview])
async def get_tenders(
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> List[TenderOverview]:
    return await load_tenders(session)


@router.post('/tenders', response_model=TenderOverview, status_code=status.HTTP_201_CREATED)
async def create_tender(
    body: TenderCreate,
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> TenderOverview:
    tender = Tender(
        name=body.name,
        customer=body.customer,
        city=body.city,
        status=TenderStatus.new,
        deadline=body.deadline,
    )
    session.add(tender)
    await session.commit()
    records = await load_tenders(session)
    for record in records:
        if record.id == tender.id:
            return record
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build tender payload')


@router.get('/tenders/{tender_id}', response_model=TenderOverview)
async def get_tender(
    tender_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> TenderOverview:
    records = await load_tenders(session)
    for record in records:
        if record.id == tender_id:
            return record
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tender not found')


@router.patch('/tenders/{tender_id}/status', response_model=TenderOverview)
async def update_tender_status(
    tender_id: UUID,
    body: TenderStatusUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> TenderOverview:
    tender = await session.get(Tender, tender_id)
    if not tender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tender not found')
    if body.status == TenderStatus.completed:
        not_completed = (await session.scalars(
            select(Task).join(Building).where(
                Building.tender_id == tender.id,
                Task.status.notin_([TaskStatus.completed, TaskStatus.canceled]),
            )
        )).all()
        if not_completed:
            blockers = [f"Task {task.id} status={task.status.value}" for task in not_completed]
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=blockers)
    tender.status = body.status
    if body.status == TenderStatus.completed:
        tender.closed_at = datetime.utcnow()
    session.add(tender)
    await session.commit()
    records = await load_tenders(session)
    for record in records:
        if record.id == tender.id:
            return record
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build tender payload')


@router.get('/tenders/{tender_id}/dashboard', response_model=TenderDashboardRead)
async def get_tender_dashboard(
    tender_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> TenderDashboardRead:
    tender = await session.get(Tender, tender_id)
    if not tender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tender not found')
    buildings = (await session.scalars(select(Building).where(Building.tender_id == tender.id))).all()
    building_ids = [building.id for building in buildings]
    if building_ids:
        tasks = (await session.scalars(select(Task).where(Task.building_id.in_(building_ids)))).all()
    else:
        tasks = []
    task_count = len(tasks)
    completed_tasks = sum(1 for task in tasks if task.status in {TaskStatus.completed, TaskStatus.canceled})
    in_progress_tasks = sum(1 for task in tasks if task.status in {TaskStatus.assigned, TaskStatus.in_progress})
    pending_tasks = sum(1 for task in tasks if task.status == TaskStatus.pending)
    progress_pct = round((completed_tasks / task_count) * 100, 2) if task_count else 0.0
    active_brigades = len({str(task.brigade_id) for task in tasks if task.brigade_id})
    planned_cable = 0.0
    for building in buildings:
        entrances = building.entrances_count or 1
        floors = building.floors_count or 1
        floor_height = building.floor_height_m or 2.8
        distance = building.distance_from_muffle_m or 0.0
        reserve = building.cable_reserve_pct or 15
        planned_cable += (entrances * floors * floor_height + distance) * (1 + reserve / 100)
    return TenderDashboardRead(
        tender_id=tender.id,
        progress_pct=progress_pct,
        building_count=len(buildings),
        task_count=task_count,
        completed_tasks=completed_tasks,
        in_progress_tasks=in_progress_tasks,
        pending_tasks=pending_tasks,
        active_brigades=active_brigades,
        planned_cable_meters=round(planned_cable, 1),
    )


@router.post('/tenders/{tender_id}/complete', response_model=TenderCompleteRead)
async def complete_tender(
    tender_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = designer_only,
) -> TenderCompleteRead:
    tender = await session.get(Tender, tender_id)
    if not tender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tender not found')
    blockers_tasks = (await session.scalars(
        select(Task).join(Building).where(
            Building.tender_id == tender.id,
            Task.status.notin_([TaskStatus.completed, TaskStatus.canceled]),
        )
    )).all()
    if blockers_tasks:
        blockers = [f"Task {task.id} status={task.status.value}" for task in blockers_tasks]
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=blockers)
    tender.status = TenderStatus.completed
    tender.closed_at = datetime.utcnow()
    session.add(tender)
    await session.commit()
    return TenderCompleteRead(
        tender_id=tender.id,
        status=tender.status,
        completed_at=tender.closed_at or datetime.utcnow(),
        handover_summary=f"Tender {tender.name} marked completed and ready for infrastructure handover",
        blockers=[],
    )

@router.get('/stock', response_model=List[StockItemRead])
async def get_stock(
    session: AsyncSession = Depends(get_session),
    _: User = warehouse_or_designer,
) -> List[StockItemRead]:
    return await load_stock_items(session)


@router.get('/stock/transactions', response_model=List[StockTransactionRead])
async def get_stock_transactions(
    session: AsyncSession = Depends(get_session),
    _: User = warehouse_only,
) -> List[StockTransactionRead]:
    return await load_stock_transactions(session)


@router.post('/stock/adjust', response_model=StockItemRead)
async def adjust_stock(
    body: StockAdjustRequest,
    session: AsyncSession = Depends(get_session),
    warehouse_user: User = warehouse_only,
) -> StockItemRead:
    item = await session.get(StockItem, body.stock_item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Stock item not found')
    next_quantity = item.quantity + body.delta
    if next_quantity < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Stock quantity cannot become negative')
    item.quantity = next_quantity
    item.updated_at = datetime.utcnow()
    session.add(item)
    session.add(StockTransaction(
        stock_item_id=item.id,
        delta=body.delta,
        reason=body.reason,
        user_id=warehouse_user.id,
    ))
    session.add(WorkLog(
        user_id=warehouse_user.id,
        event_type='stock.adjusted',
        description=f'{item.name}: {body.delta}',
        quantity=abs(body.delta),
        unit=item.unit,
        event_at=datetime.utcnow(),
    ))
    await session.commit()
    await session.refresh(item)
    return StockItemRead(
        id=item.id,
        name=item.name,
        unit=item.unit,
        quantity=item.quantity,
        min_quantity=item.min_quantity,
        shortage=item.quantity < item.min_quantity,
    )

@router.get('/warehouse/requests', response_model=List[WarehouseRequestRead])
async def get_requests(
    session: AsyncSession = Depends(get_session),
    _: User = warehouse_only,
) -> List[WarehouseRequestRead]:
    return await load_warehouse_requests(session)


@router.post('/warehouse/requests', response_model=WarehouseRequestRead, status_code=status.HTTP_201_CREATED)
async def create_request(
    body: WarehouseRequestCreate,
    session: AsyncSession = Depends(get_session),
    warehouse_user: User = warehouse_only,
) -> WarehouseRequestRead:
    if not body.items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Warehouse request requires at least one item')
    req = WarehouseRequest(
        requested_by=warehouse_user.id,
        task_id=body.task_id,
        building_id=body.building_id,
        notes=body.notes,
    )
    session.add(req)
    await session.flush()
    for entry in body.items:
        stock_item = await session.get(StockItem, entry.stock_item_id)
        if not stock_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Stock item not found: {entry.stock_item_id}')
        session.add(WarehouseRequestItem(
            request_id=req.id,
            stock_item_id=entry.stock_item_id,
            planned_qty=entry.planned_qty,
        ))
    session.add(WorkLog(
        user_id=warehouse_user.id,
        task_id=body.task_id,
        event_type='warehouse.request.created',
        description=body.notes or 'Manual warehouse request',
        quantity=float(len(body.items)),
        unit='item',
        event_at=datetime.utcnow(),
    ))
    await session.commit()
    records = await load_warehouse_requests(session)
    for record in records:
        if record.id == req.id:
            return record
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build warehouse request payload')


@router.post('/warehouse/requests/{request_id}/fulfill', response_model=WarehouseRequestRead)
async def fulfill_request(
    request_id: UUID,
    body: WarehouseRequestFulfill,
    session: AsyncSession = Depends(get_session),
    warehouse_user: User = warehouse_only,
) -> WarehouseRequestRead:
    req = await session.get(WarehouseRequest, request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Warehouse request not found')
    if req.status == RequestStatus.fulfilled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Warehouse request already fulfilled')

    items = (await session.scalars(
        select(WarehouseRequestItem)
        .options(selectinload(WarehouseRequestItem.stock_item))
        .where(WarehouseRequestItem.request_id == req.id)
    )).all()
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Warehouse request has no items')

    requested_map = {entry.item_id: entry.fulfilled_qty for entry in body.items}
    any_progress = False
    all_fulfilled = True

    for item in items:
        stock_item = item.stock_item
        if not stock_item:
            continue
        already_fulfilled = item.fulfilled_qty or 0.0
        remaining = max(0.0, item.planned_qty - already_fulfilled)
        requested_qty = requested_map.get(item.id, remaining)
        qty_to_fulfill = min(remaining, requested_qty, max(0.0, stock_item.quantity))
        if qty_to_fulfill > 0:
            stock_item.quantity -= qty_to_fulfill
            item.fulfilled_qty = already_fulfilled + qty_to_fulfill
            session.add(stock_item)
            session.add(item)
            session.add(StockTransaction(
                stock_item_id=stock_item.id,
                delta=-qty_to_fulfill,
                reason=f'warehouse_request:{req.id}',
                task_id=req.task_id,
                user_id=warehouse_user.id,
            ))
            session.add(WorkLog(
                user_id=warehouse_user.id,
                task_id=req.task_id,
                event_type='warehouse.request.fulfilled',
                description=f'{stock_item.name}: {qty_to_fulfill}',
                quantity=qty_to_fulfill,
                unit=stock_item.unit,
                event_at=datetime.utcnow(),
            ))
            any_progress = True
        if (item.fulfilled_qty or 0.0) < item.planned_qty:
            all_fulfilled = False

    if not any_progress:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='No stock available to fulfill request')

    req.status = RequestStatus.fulfilled if all_fulfilled else RequestStatus.partial
    if req.status == RequestStatus.fulfilled:
        req.fulfilled_at = datetime.utcnow()
    session.add(req)
    await session.commit()

    records = await load_warehouse_requests(session)
    for record in records:
        if record.id == req.id:
            return record
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build warehouse request payload')


@router.get('/field/metrics', response_model=FieldMetrics)
async def get_field_metrics(
    session: AsyncSession = Depends(get_session),
    _: User = field_roles,
) -> FieldMetrics:
    return await load_field_metrics(session)


@router.get('/tasks/{task_id}/work-summary', response_model=WorkSummaryRead)
async def get_task_work_summary(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> WorkSummaryRead:
    summary = await load_task_work_summary(session, task_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    return summary


@router.get('/tasks/{task_id}/comments', response_model=List[OpsCommentRead])
async def get_task_comments(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> List[OpsCommentRead]:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    comments = (await session.scalars(
        select(OpsComment)
        .options(selectinload(OpsComment.author))
        .where(OpsComment.task_id == task_id)
        .order_by(OpsComment.created_at.desc())
    )).all()
    from ..services.logic import serialize_ops_comment
    return [serialize_ops_comment(comment) for comment in comments]


@router.post('/tasks/{task_id}/comments', response_model=OpsCommentRead, status_code=status.HTTP_201_CREATED)
async def create_task_comment(
    task_id: UUID,
    body: OpsCommentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = ops_roles,
) -> OpsCommentRead:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    comment = OpsComment(
        task_id=task_id,
        author_id=current_user.id,
        comment_type=body.comment_type,
        body=body.body,
        role_tags=_role_tag_values(body.role_tags),
    )
    session.add(comment)
    await session.commit()
    comment = (await session.scalars(
        select(OpsComment).options(selectinload(OpsComment.author)).where(OpsComment.id == comment.id)
    )).one()
    from ..services.logic import serialize_ops_comment
    return serialize_ops_comment(comment)


@router.get('/tasks/{task_id}/contacts', response_model=List[OpsContactRead])
async def get_task_contacts(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> List[OpsContactRead]:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    contacts = (await session.scalars(
        select(OpsContact).where(OpsContact.task_id == task_id).order_by(OpsContact.created_at.desc())
    )).all()
    from ..services.logic import serialize_ops_contact
    return [serialize_ops_contact(contact) for contact in contacts]


@router.post('/tasks/{task_id}/contacts', response_model=OpsContactRead, status_code=status.HTTP_201_CREATED)
async def create_task_contact(
    task_id: UUID,
    body: OpsContactCreate,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> OpsContactRead:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    contact = OpsContact(
        task_id=task_id,
        title=body.title,
        full_name=body.full_name,
        phone=body.phone,
        notes=body.notes,
    )
    session.add(contact)
    await session.commit()
    from ..services.logic import serialize_ops_contact
    return serialize_ops_contact(contact)


@router.post('/tasks/{task_id}/reports', response_model=TaskReportRead, status_code=status.HTTP_201_CREATED)
async def create_task_report(
    request: Request,
    task_id: UUID,
    body: TaskReportCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = field_roles,
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
        user_id=current_user.id,
        photo_url=photo_url,
        comment=body.comment,
        brigade_id=body.brigade_id,
        brigade_name=brigade_name,
    )
    session.add(report)
    session.add(WorkLog(
        user_id=current_user.id,
        task_id=task.id,
        event_type='task.photo.reported',
        description=body.comment or photo_url,
        quantity=1.0,
        unit='photo',
        event_at=report.created_at,
    ))
    await session.commit()
    await session.refresh(report)
    payload = {
        'event_type': 'task.photo.reported',
        'task_id': str(task.id),
        'brigade_id': str(body.brigade_id) if body.brigade_id else None,
        'brigade_name': report.brigade_name,
        'photo_url': report.photo_url,
        'comment': report.comment,
        'created_at': report.created_at.isoformat(),
        'event_at': report.created_at.isoformat(),
        'recorded_at': _now_iso(),
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
        event_at=report.created_at,
    )
