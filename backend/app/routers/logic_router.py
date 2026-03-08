from datetime import datetime
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
    Brigade,
    Building,
    Fiber,
    FiberStatus,
    InfraStatus,
    Muffle,
    Panel,
    Port,
    PortStatus,
    RequestStatus,
    StockItem,
    Task,
    TaskReport,
    TaskStatus,
    TaskStep,
    TaskType,
    Tender,
    TenderStatus,
    User,
    UserRole,
    WarehouseRequest,
    WarehouseRequestItem,
)
from ..rate_limit import enforce_http_rate_limit
from ..schemas import (
    BrigadeBoardItem,
    TaskAssignRequest,
    TaskQueueItem,
    TaskStepRead,
    TaskStepCompleteRead,
    TimelineHour,
    StockItemRead,
    WarehouseRequestRead,
    NetworkMuffleRead,
    TenderOverview,
    TenderCreate,
    TenderStatusUpdate,
    TenderDashboardRead,
    TenderCompleteRead,
    BuildingNetworkRead,
    NetworkOverview,
    BuildingCalculateRead,
    MuffleCapacityRead,
    MuffleCapacityFiberRead,
    InfrastructureBuildingRead,
    InfrastructurePanelRead,
    InfrastructurePortRead,
    TaskReportCreate,
    TaskReportRead,
    FieldMetrics,
    NetworkPlanCreate,
    NetworkPlanRead,
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


@router.get('/tasks/{task_id}/steps', response_model=List[TaskStepRead])
async def get_task_steps(task_id: UUID, session: AsyncSession = Depends(get_session)) -> List[TaskStepRead]:
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
) -> TaskStepCompleteRead:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    step = await session.get(TaskStep, step_id)
    if not step or step.task_id != task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Step not found')
    step.is_done = True
    step.done_at = datetime.utcnow()
    task.status = TaskStatus.in_progress
    session.add(step)
    session.add(task)
    await session.flush()
    await refresh_tender_and_building_state(session, task)
    await session.commit()
    payload = {
        'task_id': str(task.id),
        'step': step.title,
        'timestamp': step.done_at.isoformat() if step.done_at else datetime.utcnow().isoformat(),
    }
    await realtime_manager.broadcast_event('progress.update', payload, room='dispatchers')
    return TaskStepCompleteRead(
        task_id=task.id,
        step_id=step.id,
        is_done=step.is_done,
        done_at=step.done_at,
    )

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


@router.post('/network/buildings/{building_id}/calculate', response_model=BuildingCalculateRead)
async def calculate_building_network(building_id: UUID, session: AsyncSession = Depends(get_session)) -> BuildingCalculateRead:
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
async def get_muffle_capacity(muffle_id: UUID, session: AsyncSession = Depends(get_session)) -> MuffleCapacityRead:
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
async def get_infrastructure_registry(session: AsyncSession = Depends(get_session)) -> List[InfrastructureBuildingRead]:
    buildings = (await session.scalars(
        select(Building).where(Building.infrastructure_status == InfraStatus.completed)
    )).all()
    payload: list[InfrastructureBuildingRead] = []
    for building in buildings:
        panels = (await session.scalars(
            select(Panel).options(selectinload(Panel.ports)).where(Panel.building_id == building.id)
        )).all()
        panel_items: list[InfrastructurePanelRead] = []
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
            panel_items.append(InfrastructurePanelRead(
                panel_id=panel.id,
                entrance_num=panel.entrance_num,
                floor_num=panel.floor_num,
                label=panel.label,
                ports=ports,
            ))
        payload.append(InfrastructureBuildingRead(
            building_id=building.id,
            address=building.address,
            city=building.city,
            infrastructure_status=building.infrastructure_status.value if isinstance(building.infrastructure_status, InfraStatus) else str(building.infrastructure_status),
            panels=panel_items,
        ))
    return payload


@router.get('/tenders', response_model=List[TenderOverview])
async def get_tenders(session: AsyncSession = Depends(get_session)) -> List[TenderOverview]:
    return await load_tenders(session)


@router.post('/tenders', response_model=TenderOverview, status_code=status.HTTP_201_CREATED)
async def create_tender(body: TenderCreate, session: AsyncSession = Depends(get_session)) -> TenderOverview:
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
async def get_tender(tender_id: UUID, session: AsyncSession = Depends(get_session)) -> TenderOverview:
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
async def get_tender_dashboard(tender_id: UUID, session: AsyncSession = Depends(get_session)) -> TenderDashboardRead:
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
async def complete_tender(tender_id: UUID, session: AsyncSession = Depends(get_session)) -> TenderCompleteRead:
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
