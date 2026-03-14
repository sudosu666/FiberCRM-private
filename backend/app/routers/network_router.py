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



