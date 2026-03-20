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
    TaskMaterialFact,
    TaskReport,
    TaskStatus,
    TaskStep,
    TaskType,
    Tender,
    TenderStatus,
    User,
    UserRole,
    WorkEntry,
    WorkRate,
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
    TaskCompleteActualsRequest,
    TaskCompleteActualsRead,
    TaskMaterialFactRead,
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


async def _ensure_rate(
    session: AsyncSession,
    *,
    code: str,
    title: str,
    unit: str,
    price_uah: float,
) -> WorkRate:
    rate = (await session.scalars(select(WorkRate).where(WorkRate.code == code).limit(1))).first()
    if rate:
        return rate
    rate = WorkRate(
        code=code,
        title=title,
        unit=unit,
        price_uah=price_uah,
        is_active=True,
        updated_at=datetime.utcnow(),
    )
    session.add(rate)
    await session.flush()
    return rate


def _stock_category(stock_item_name: Optional[str]) -> Optional[str]:
    name = (stock_item_name or "").lower()
    if "кабел" in name or "окл" in name:
        return "cable"
    if "труб" in name:
        return "tube"
    if "бокс" in name or "щит" in name:
        return "box"
    if "фоп" in name or "муфт" in name:
        return "fop"
    return None

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
    if task.type in (TaskType.construction, TaskType.welding):
        latest_request = (await session.scalars(
            select(WarehouseRequest)
            .where(WarehouseRequest.task_id == task.id)
            .order_by(WarehouseRequest.created_at.desc())
            .limit(1)
        )).first()
        if not latest_request:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Спочатку оформіть запит матеріалів і дочекайтесь підтвердження складу.',
            )
        if latest_request.status != RequestStatus.fulfilled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Склад ще не підтвердив видачу матеріалів для цієї задачі.',
            )
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


@router.patch('/tasks/{task_id}/complete-with-actuals', response_model=TaskCompleteActualsRead)
async def complete_task_with_actuals(
    task_id: UUID,
    body: TaskCompleteActualsRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = field_roles,
) -> TaskCompleteActualsRead:
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

    rate_specs = [
        ("cable_inside_m", "Прокладка кабеля (всередині)", "m", 18.0, body.cable_indoor_m),
        ("cable_outside_m", "Прокладка кабеля (зовні)", "m", 24.0, body.cable_outdoor_m),
        ("cable_air_m", "Прокладка кабеля по повітрю", "m", 32.0, body.cable_air_m),
        ("tube_between_floors", "Трубка між поверхами", "unit", 120.0, body.tubes_qty),
        ("box_installed", "Встановлений бокс", "unit", 450.0, body.boxes_qty),
        ("fop_installed", "Встановлений ФОП/муфта", "unit", 350.0, body.fops_qty),
        ("cable_waste_m", "Списання кабеля (непродуктивне)", "m", 0.0, body.cable_wasted_m),
    ]

    for code, title, unit, default_price, qty in rate_specs:
        if qty <= 0:
            continue
        rate = await _ensure_rate(
            session,
            code=code,
            title=title,
            unit=unit,
            price_uah=default_price,
        )
        session.add(WorkEntry(
            task_id=task.id,
            brigade_id=task.brigade_id,
            user_id=current_user.id,
            work_rate_id=rate.id,
            work_code=rate.code,
            title=rate.title,
            quantity=qty,
            unit=rate.unit,
            unit_price_uah=rate.price_uah,
            total_price_uah=round(float(qty) * float(rate.price_uah or 0.0), 2),
            notes=body.notes,
            event_at=event_at,
        ))

    taken_by_category = {"cable": 0.0, "tube": 0.0, "box": 0.0, "fop": 0.0}
    txs = (await session.scalars(
        select(StockTransaction)
        .options(selectinload(StockTransaction.stock_item))
        .where(StockTransaction.task_id == task.id)
    )).all()
    for tx in txs:
        if (tx.delta or 0.0) >= 0:
            continue
        if not (tx.reason or "").startswith("warehouse_request:"):
            continue
        category = _stock_category(tx.stock_item.name if tx.stock_item else None)
        if not category:
            continue
        taken_by_category[category] += abs(float(tx.delta or 0.0))

    used_by_category = {
        "cable": float(body.cable_indoor_m + body.cable_outdoor_m + body.cable_air_m),
        "tube": float(body.tubes_qty),
        "box": float(body.boxes_qty),
        "fop": float(body.fops_qty),
    }
    wasted_by_category = {
        "cable": float(body.cable_wasted_m),
        "tube": 0.0,
        "box": 0.0,
        "fop": 0.0,
    }
    meta = {
        "cable": ("cable_total", "Кабель загалом", "m"),
        "tube": ("tube_total", "Трубка", "unit"),
        "box": ("box_total", "Бокс", "unit"),
        "fop": ("fop_total", "ФОП/Муфта", "unit"),
    }

    facts: list[TaskMaterialFactRead] = []
    for category, (code, title, unit) in meta.items():
        taken_qty = round(taken_by_category.get(category, 0.0), 2)
        used_qty = round(used_by_category.get(category, 0.0), 2)
        wasted_qty = round(wasted_by_category.get(category, 0.0), 2)
        delta_qty = round(taken_qty - used_qty - wasted_qty, 2)
        fact = (await session.scalars(
            select(TaskMaterialFact).where(TaskMaterialFact.task_id == task.id, TaskMaterialFact.material_code == code).limit(1)
        )).first()
        if not fact:
            fact = TaskMaterialFact(
                task_id=task.id,
                material_code=code,
                material_title=title,
                unit=unit,
            )
        fact.taken_qty = taken_qty
        fact.used_qty = used_qty
        fact.wasted_qty = wasted_qty
        fact.delta_qty = delta_qty
        fact.recorded_at = event_at
        session.add(fact)
        facts.append(TaskMaterialFactRead(
            material_code=code,
            material_title=title,
            unit=unit,
            taken_qty=taken_qty,
            used_qty=used_qty,
            wasted_qty=wasted_qty,
            delta_qty=delta_qty,
        ))

    session.add(WorkLog(
        user_id=current_user.id,
        task_id=task.id,
        event_type='task.completed.with_actuals',
        description='Task completed with actuals and deltas',
        quantity=1.0,
        unit='task',
        event_at=event_at,
    ))

    await session.flush()
    await refresh_tender_and_building_state(session, task)

    payout_entries = (await session.scalars(select(WorkEntry).where(WorkEntry.task_id == task.id))).all()
    brigade_total_amount = round(sum(float(item.total_price_uah or 0.0) for item in payout_entries), 2)
    member_ids: set[UUID] = set()
    if task.brigade_id:
        members = (await session.scalars(select(BrigadeMember).where(BrigadeMember.brigade_id == task.brigade_id))).all()
        member_ids.update(item.user_id for item in members)
        brigade = await session.get(Brigade, task.brigade_id)
        if brigade and brigade.foreman_id:
            member_ids.add(brigade.foreman_id)
    members_count = max(1, len(member_ids))
    per_member_amount = round(brigade_total_amount / float(members_count), 2)

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
    return TaskCompleteActualsRead(
        task_id=task.id,
        status=task.status,
        event_at=event_at,
        brigade_id=task.brigade_id,
        brigade_total_amount_uah=brigade_total_amount,
        brigade_members_count=members_count,
        per_member_amount_uah=per_member_amount,
        facts=facts,
    )


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


@router.patch('/tasks/{task_id}/unassign', response_model=TaskQueueItem)
async def unassign_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = dispatcher_only,
) -> TaskQueueItem:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    if not task.brigade_id:
        queue = await load_task_queue(session)
        for item in queue:
            if item.id == task.id:
                return item
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build task payload')

    prev_brigade_id = task.brigade_id
    if task.status == TaskStatus.assigned:
        task.status = TaskStatus.pending
    task.brigade_id = None
    task.hold_reason = None
    task.is_critical = False
    session.add(task)
    session.add(WorkLog(
        user_id=current_user.id,
        task_id=task.id,
        event_type='task.unassigned',
        description=f'Unassigned from brigade {prev_brigade_id}',
        quantity=1.0,
        unit='task',
        event_at=datetime.utcnow(),
    ))
    await session.flush()
    await refresh_tender_and_building_state(session, task)
    await session.commit()

    queue = await load_task_queue(session)
    await realtime_manager.broadcast_event('queue.update', {
        'event_type': 'queue.update',
        'event_at': _now_iso(),
        'recorded_at': _now_iso(),
        'items': [item.model_dump(mode='json') for item in queue],
    }, room='dispatchers')
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


@router.patch('/brigades/{brigade_id}/active', response_model=BrigadeBoardItem)
async def set_brigade_active(
    brigade_id: UUID,
    is_active: bool,
    session: AsyncSession = Depends(get_session),
    current_user: User = dispatcher_only,
) -> BrigadeBoardItem:
    brigade = await session.get(Brigade, brigade_id)
    if not brigade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Brigade not found')
    brigade.is_active = is_active
    session.add(brigade)
    session.add(WorkLog(
        user_id=current_user.id,
        event_type='brigade.activation.changed',
        description=f'{brigade.name}: {"active" if is_active else "inactive"}',
        quantity=1.0,
        unit='brigade',
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


@router.delete('/brigades/{brigade_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_brigade(
    brigade_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = dispatcher_only,
) -> None:
    brigade = await session.get(Brigade, brigade_id)
    if not brigade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Brigade not found')

    brigade_tasks = (await session.scalars(select(Task).where(Task.brigade_id == brigade.id))).all()
    for task in brigade_tasks:
        task.brigade_id = None
        if task.status == TaskStatus.assigned:
            task.status = TaskStatus.pending
        task.hold_reason = None
        task.is_critical = False
        session.add(task)
        await refresh_tender_and_building_state(session, task)

    members = (await session.scalars(select(BrigadeMember).where(BrigadeMember.brigade_id == brigade.id))).all()
    members_count = len(members)
    for member in members:
        await session.delete(member)

    name = brigade.name
    await session.delete(brigade)
    session.add(WorkLog(
        user_id=current_user.id,
        event_type='brigade.deleted',
        description=f'{name}',
        quantity=float(members_count),
        unit='member',
        event_at=datetime.utcnow(),
    ))
    await session.commit()

    board = await load_brigade_board(session)
    queue = await load_task_queue(session)
    await realtime_manager.broadcast_event('brigade_board.update', {
        'event_type': 'brigade_board.update',
        'event_at': _now_iso(),
        'recorded_at': _now_iso(),
        'items': [item.model_dump(mode='json') for item in board],
    })
    await realtime_manager.broadcast_event('queue.update', {
        'event_type': 'queue.update',
        'event_at': _now_iso(),
        'recorded_at': _now_iso(),
        'items': [item.model_dump(mode='json') for item in queue],
    }, room='dispatchers')

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


@router.get('/tasks/{task_id}/material-facts', response_model=List[TaskMaterialFactRead])
async def get_task_material_facts(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> List[TaskMaterialFactRead]:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    facts = (await session.scalars(
        select(TaskMaterialFact)
        .where(TaskMaterialFact.task_id == task.id)
        .order_by(TaskMaterialFact.material_title.asc())
    )).all()
    return [
        TaskMaterialFactRead(
            material_code=fact.material_code,
            material_title=fact.material_title,
            unit=fact.unit,
            taken_qty=fact.taken_qty,
            used_qty=fact.used_qty,
            wasted_qty=fact.wasted_qty,
            delta_qty=fact.delta_qty,
        )
        for fact in facts
    ]


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
