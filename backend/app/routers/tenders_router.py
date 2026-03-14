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


