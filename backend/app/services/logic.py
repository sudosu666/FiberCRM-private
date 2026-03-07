from math import ceil
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import (
    Building,
    Brigade,
    Fiber,
    Muffle,
    StockItem,
    Task,
    TaskStatus,
    WarehouseRequest,
    WarehouseRequestItem,
)
from ..schemas import (
    BuildingMetrics,
    BrigadeBoardItem,
    BrigadeTaskSummary,
    NetworkFiberRead,
    NetworkMuffleRead,
    StockItemRead,
    TaskQueueItem,
    TimelineBlock,
    TimelineHour,
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
