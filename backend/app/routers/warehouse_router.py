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



