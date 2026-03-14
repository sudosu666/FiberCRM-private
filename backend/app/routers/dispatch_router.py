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

@router.get('/field/workers', response_model=List[FieldWorkerRead])
async def get_field_workers(
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> List[FieldWorkerRead]:
    return await load_field_workers(session)


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

@router.get('/field/metrics', response_model=FieldMetrics)
async def get_field_metrics(
    session: AsyncSession = Depends(get_session),
    _: User = field_roles,
) -> FieldMetrics:
    return await load_field_metrics(session)



