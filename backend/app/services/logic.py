from math import ceil
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import (
    Building,
    Brigade,
    Fiber,
    FiberStatus,
    InfraStatus,
    Muffle,
    Port,
    PortStatus,
    StockItem,
    Task,
    TaskStatus,
    Tender,
    TenderStatus,
    WarehouseRequest,
    WarehouseRequestItem,
)
from ..schemas import (
    BuildingMetrics,
    BrigadeBoardItem,
    BrigadeTaskSummary,
    NetworkFiberRead,
    NetworkMuffleRead,
    NetworkOverview,
    BuildingNetworkRead,
    StockItemRead,
    TaskQueueItem,
    TimelineBlock,
    TimelineHour,
    TenderOverview,
    WarehouseRequestItemRead,
    WarehouseRequestRead,
)


def calculate_building_metrics(building: Building) -> BuildingMetrics:
    entrances = building.entrances_count or 1
    floors = building.floors_count or 1
    panel_every = building.panel_every_n_floors or 5
    panels = entrances * ceil(floors / panel_every) if panel_every else entrances
    floor_height = building.floor_height_m or 2.8
    distance = building.distance_from_muffle_m or 0.0
    reserve_pct = building.cable_reserve_pct or 15
    planned = (entrances * floors * floor_height + distance) * (1 + reserve_pct / 100)
    total_flats = entrances * floors * (building.flats_per_floor or 1)
    return BuildingMetrics(
        planned_cable_meters=round(planned, 1),
        panels_count=panels,
        total_flats=total_flats,
        distance_from_muffle=distance,
        cable_reserve_pct=reserve_pct,
    )


def _task_progress_pct(task: Task) -> int:
    if task.status == TaskStatus.completed:
        return 100
    if task.status == TaskStatus.in_progress:
        return 60
    if task.status == TaskStatus.assigned:
        return 35
    return 10


def task_to_queue_item(task: Task) -> TaskQueueItem:
    building_address = task.building.address if task.building else None
    brigade_name = task.brigade.name if task.brigade else None
    metrics = calculate_building_metrics(task.building) if task.building else BuildingMetrics(
        planned_cable_meters=0.0,
        panels_count=0,
        total_flats=0,
        distance_from_muffle=0.0,
        cable_reserve_pct=0,
    )
    return TaskQueueItem(
        id=str(task.id),
        type=task.type,
        status=task.status,
        priority=task.priority,
        description=task.description,
        building_id=str(task.building_id) if task.building_id else None,
        building_address=building_address,
        brigade_name=brigade_name,
        estimated_hours=task.estimated_hours,
        metrics=metrics,
    )


def _to_brigade_task_summary(task: Task) -> BrigadeTaskSummary:
    address = task.building.address if task.building else None
    return BrigadeTaskSummary(
        id=str(task.id),
        type=task.type,
        status=task.status,
        priority=task.priority,
        building_address=address,
        progress_pct=_task_progress_pct(task),
    )


def _timeline_blocks(tasks: List[Task]) -> List[TimelineHour]:
    timeline = []
    hours = list(range(8, 19))
    if not tasks:
        return [TimelineHour(hour=hour, blocks=[]) for hour in hours]
    for idx, hour in enumerate(hours):
        task = tasks[idx % len(tasks)]
        if not task.brigade:
            timeline.append(TimelineHour(hour=hour, blocks=[]))
            continue
        timeline.append(TimelineHour(
            hour=hour,
            blocks=[TimelineBlock(
                label=f"{task.brigade.name} · {task.building.address if task.building else '—'}",
                duration_hours=round((task.estimated_hours or 2), 1),
            )],
        ))
    return timeline


def _network_fibers_for_muffle(muffle: Muffle, fibers: List[Fiber]) -> List[NetworkFiberRead]:
    return [NetworkFiberRead(id=str(f.id), fiber_number=f.fiber_number, status=f.status.value) for f in fibers]


async def load_task_queue(session: AsyncSession) -> List[TaskQueueItem]:
    stmt = select(Task).options(selectinload(Task.building), selectinload(Task.brigade))
    result = await session.scalars(stmt)
    tasks = result.all()
    return [task_to_queue_item(task) for task in tasks]


async def load_brigade_board(session: AsyncSession) -> List[BrigadeBoardItem]:
    stmt = select(Brigade).options(
        selectinload(Brigade.tasks).selectinload(Task.building)
    )
    result = await session.scalars(stmt)
    brigades = result.all()
    board = []
    for brigade in brigades:
        summaries = [_to_brigade_task_summary(task) for task in brigade.tasks]
        board.append(BrigadeBoardItem(
            id=str(brigade.id),
            name=brigade.name,
            type=brigade.type,
            members=len(brigade.members) if brigade.members else 0,
            is_active=brigade.is_active,
            tasks=summaries,
            status_label='В роботі' if brigade.is_active else 'Офлайн',
        ))
    return board


async def load_timeline(session: AsyncSession) -> List[TimelineHour]:
    stmt = select(Task).options(selectinload(Task.building), selectinload(Task.brigade))
    result = await session.scalars(stmt)
    tasks = result.all()
    return _timeline_blocks(tasks)


async def load_stock_items(session: AsyncSession) -> List[StockItemRead]:
    stmt = select(StockItem)
    result = await session.scalars(stmt)
    items = result.all()
    return [StockItemRead(
        id=str(item.id),
        name=item.name,
        unit=item.unit,
        quantity=item.quantity,
        min_quantity=item.min_quantity,
    ) for item in items]


async def load_warehouse_requests(session: AsyncSession) -> List[WarehouseRequestRead]:
    stmt = select(WarehouseRequest).options(selectinload(WarehouseRequest.items).selectinload(WarehouseRequestItem.stock_item))
    result = await session.scalars(stmt)
    requests = result.all()
    records = []
    for req in requests:
        records.append(WarehouseRequestRead(
            id=str(req.id),
            building_address=req.building.address if req.building else None,
            status=req.status.value,
            notes=req.notes,
            created_at=req.created_at,
            items=[WarehouseRequestItemRead(
                stock_item_name=item.stock_item.name,
                planned_qty=item.planned_qty,
                fulfilled_qty=item.fulfilled_qty,
            ) for item in req.items],
        ))
    return records


async def load_network_topology(session: AsyncSession) -> List[NetworkMuffleRead]:
    stmt = select(Muffle).options(selectinload(Muffle.fibers))
    result = await session.scalars(stmt)
    muffles = result.all()
    return [NetworkMuffleRead(
        id=str(muffle.id),
        name=muffle.name,
        address_note=muffle.address_note,
        capacity=muffle.capacity,
        fibers=_network_fibers_for_muffle(muffle, muffle.fibers),
    ) for muffle in muffles]


async def load_tenders(session: AsyncSession) -> List[TenderOverview]:
    stmt = select(Tender).options(
        selectinload(Tender.buildings).selectinload(Building.tasks)
    )
    result = await session.scalars(stmt)
    records = []
    for tender in result.all():
        buildings = tender.buildings or []
        tasks = [task for building in buildings for task in (building.tasks or [])]
        statuses = [task.status for task in tasks if task.status] if tasks else []
        completed = sum(1 for status in statuses if _is_completed_status(status))
        in_progress = sum(1 for status in statuses if _is_in_progress_status(status))
        pending = sum(1 for status in statuses if status == TaskStatus.pending)
        planned_cable = sum(calculate_building_metrics(building).planned_cable_meters for building in buildings)
        records.append(TenderOverview(
            id=tender.id,
            name=tender.name,
            status=tender.status,
            customer=tender.customer,
            city=tender.city,
            building_count=len(buildings),
            task_count=len(tasks),
            completed_tasks=completed,
            in_progress_tasks=in_progress,
            pending_tasks=pending,
            planned_cable_meters=round(planned_cable, 1),
        ))
    return records


async def load_network_overview(session: AsyncSession) -> NetworkOverview:
    fibers = (await session.scalars(select(Fiber))).all()
    ports = (await session.scalars(select(Port))).all()
    return NetworkOverview(
        total_fibers=len(fibers),
        reserved_fibers=sum(1 for fiber in fibers if fiber.status == FiberStatus.reserved),
        busy_fibers=sum(1 for fiber in fibers if fiber.status == FiberStatus.busy),
        total_ports=len(ports),
        reserved_ports=sum(1 for port in ports if port.status == PortStatus.reserved),
        active_ports=sum(1 for port in ports if port.status == PortStatus.active),
        faulty_ports=sum(1 for port in ports if port.status == PortStatus.faulty),
    )


async def load_building_network(session: AsyncSession, building_id: UUID) -> Optional[BuildingNetworkRead]:
    building = await session.get(Building, building_id)
    if not building:
        return None
    metrics = calculate_building_metrics(building)
    return BuildingNetworkRead(
        id=building.id,
        address=building.address,
        metrics=metrics,
    )


async def refresh_tender_and_building_state(session: AsyncSession, task: Task) -> None:
    if not task.building_id:
        return
    building = await session.get(Building, task.building_id)
    if not building:
        return
    status_records = (await session.scalars(select(Task.status).where(Task.building_id == building.id))).all()
    infra_status = _determine_infra_status(status_records)
    if building.infrastructure_status != infra_status:
        building.infrastructure_status = infra_status
        session.add(building)
    if not building.tender_id:
        return
    tender = await session.get(Tender, building.tender_id)
    if not tender:
        return
    tender_status_records = (await session.scalars(
        select(Task.status).join(Building).where(Building.tender_id == tender.id)
    )).all()
    new_status = _determine_tender_status(tender_status_records)
    if tender.status != new_status:
        tender.status = new_status
        session.add(tender)


def _determine_infra_status(statuses: List[TaskStatus]) -> InfraStatus:
    if not statuses:
        return InfraStatus.planned
    if all(_is_completed_status(status) for status in statuses):
        return InfraStatus.completed
    if any(_is_in_progress_status(status) for status in statuses):
        return InfraStatus.in_progress
    return InfraStatus.planned


def _determine_tender_status(statuses: List[TaskStatus]) -> TenderStatus:
    if not statuses:
        return TenderStatus.new
    if all(_is_completed_status(status) for status in statuses):
        return TenderStatus.completed
    if any(_is_in_progress_status(status) for status in statuses):
        return TenderStatus.in_progress
    return TenderStatus.planning


def _is_completed_status(status: TaskStatus) -> bool:
    return status in {TaskStatus.completed, TaskStatus.canceled}


def _is_in_progress_status(status: TaskStatus) -> bool:
    return status in {TaskStatus.assigned, TaskStatus.in_progress}
