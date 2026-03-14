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

def _role_tag_values(tags: list[UserRole]) -> str | None:
    values = ",".join(sorted({tag.value for tag in tags})) if tags else ""
    return values or None


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



