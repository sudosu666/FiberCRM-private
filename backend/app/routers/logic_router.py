from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..models import Task, TaskStatus
from ..schemas import (
    BrigadeBoardItem,
    TaskAssignRequest,
    TaskQueueItem,
    TimelineHour,
    StockItemRead,
    WarehouseRequestRead,
    NetworkMuffleRead,
)
from ..services.logic import (
    load_brigade_board,
    load_network_topology,
    load_stock_items,
    load_task_queue,
    load_timeline,
    load_warehouse_requests,
)

router = APIRouter(prefix='/api')

@router.get('/tasks', response_model=List[TaskQueueItem])
async def get_tasks(session: AsyncSession = Depends(get_db_session)) -> List[TaskQueueItem]:
    return await load_task_queue(session)

@router.post('/tasks/{task_id}/assign', response_model=TaskQueueItem)
async def assign_task(
    task_id: str,
    body: TaskAssignRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TaskQueueItem:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    task.brigade_id = body.brigade_id
    task.status = TaskStatus.assigned
    task.assigned_at = datetime.utcnow()
    session.add(task)
    await session.commit()
    await session.refresh(task)
    queue = await load_task_queue(session)
    for item in queue:
        if item.id == str(task.id):
            return item
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unable to build task payload')

@router.get('/brigades', response_model=List[BrigadeBoardItem])
async def get_brigades(session: AsyncSession = Depends(get_db_session)) -> List[BrigadeBoardItem]:
    return await load_brigade_board(session)

@router.get('/timeline', response_model=List[TimelineHour])
async def get_timeline(session: AsyncSession = Depends(get_db_session)) -> List[TimelineHour]:
    return await load_timeline(session)

@router.get('/network/topology', response_model=List[NetworkMuffleRead])
async def get_network(session: AsyncSession = Depends(get_db_session)) -> List[NetworkMuffleRead]:
    return await load_network_topology(session)

@router.get('/stock', response_model=List[StockItemRead])
async def get_stock(session: AsyncSession = Depends(get_db_session)) -> List[StockItemRead]:
    return await load_stock_items(session)

@router.get('/warehouse/requests', response_model=List[WarehouseRequestRead])
async def get_requests(session: AsyncSession = Depends(get_db_session)) -> List[WarehouseRequestRead]:
    return await load_warehouse_requests(session)
