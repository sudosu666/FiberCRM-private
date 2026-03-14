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


@router.get('/subscriber-requests', response_model=List[SubscriberRequestRead])
async def get_subscriber_requests(
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> List[SubscriberRequestRead]:
    return await load_subscriber_requests(session)


@router.get('/subscriber-requests/summary', response_model=SubscriberDispatcherSummary)
async def get_subscriber_requests_summary(
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> SubscriberDispatcherSummary:
    return await load_subscriber_dispatch_summary(session)


@router.post('/subscriber-requests', response_model=SubscriberRequestRead, status_code=status.HTTP_201_CREATED)
async def create_subscriber_request(
    body: SubscriberRequestCreate,
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> SubscriberRequestRead:
    building = await session.get(Building, body.building_id)
    if not building:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Building not found')
    request = SubscriberRequest(
        building_id=body.building_id,
        flat_number=body.flat_number,
        customer_name=body.customer_name,
        phone=body.phone,
        notes=body.notes,
        status=SubscriberRequestStatus.new,
        deadline_at=datetime.utcnow() + timedelta(days=14),
    )
    session.add(request)
    await session.commit()
    request = (await session.scalars(
        select(SubscriberRequest)
        .options(
            selectinload(SubscriberRequest.building).selectinload(Building.panels).selectinload(Panel.ports),
            selectinload(SubscriberRequest.assigned_user),
            selectinload(SubscriberRequest.contacts),
            selectinload(SubscriberRequest.comments).selectinload(OpsComment.author),
        )
        .where(SubscriberRequest.id == request.id)
    )).one()
    from ..services.logic import serialize_subscriber_request
    return serialize_subscriber_request(request)


@router.patch('/subscriber-requests/{request_id}/schedule', response_model=SubscriberRequestRead)
async def schedule_subscriber_request(
    request_id: UUID,
    body: SubscriberRequestSchedule,
    session: AsyncSession = Depends(get_session),
    _: User = connection_dispatcher_only,
) -> SubscriberRequestRead:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    assigned_user = await session.get(User, body.assigned_user_id)
    if not assigned_user or not any(user_has_role(assigned_user, role) for role in (UserRole.Builder, UserRole.Welder, UserRole.Connector)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Assigned user should be a field technician')
    request.scheduled_date = body.scheduled_date
    request.arrival_window = ArrivalWindow(body.arrival_window.value)
    request.assigned_user_id = body.assigned_user_id
    request.status = SubscriberRequestStatus.scheduled
    session.add(request)
    await session.commit()
    request = (await session.scalars(
        select(SubscriberRequest)
        .options(
            selectinload(SubscriberRequest.building).selectinload(Building.panels).selectinload(Panel.ports),
            selectinload(SubscriberRequest.assigned_user),
            selectinload(SubscriberRequest.contacts),
            selectinload(SubscriberRequest.comments).selectinload(OpsComment.author),
        )
        .where(SubscriberRequest.id == request_id)
    )).one()
    from ..services.logic import serialize_subscriber_request
    return serialize_subscriber_request(request)


@router.patch('/subscriber-requests/{request_id}/postpone', response_model=SubscriberRequestRead)
async def postpone_subscriber_request(
    request_id: UUID,
    body: SubscriberRequestPostpone,
    session: AsyncSession = Depends(get_session),
    _: User = connection_dispatcher_only,
) -> SubscriberRequestRead:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    request.status = SubscriberRequestStatus.postponed
    session.add(request)
    session.add(OpsComment(
        subscriber_request_id=request.id,
        comment_type='postpone',
        body=body.reason,
    ))
    await session.commit()
    request = (await session.scalars(
        select(SubscriberRequest)
        .options(
            selectinload(SubscriberRequest.building).selectinload(Building.panels).selectinload(Panel.ports),
            selectinload(SubscriberRequest.assigned_user),
            selectinload(SubscriberRequest.contacts),
            selectinload(SubscriberRequest.comments).selectinload(OpsComment.author),
        )
        .where(SubscriberRequest.id == request_id)
    )).one()
    from ..services.logic import serialize_subscriber_request
    return serialize_subscriber_request(request)


@router.get('/subscriber-requests/{request_id}/comments', response_model=List[OpsCommentRead])
async def get_subscriber_request_comments(
    request_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> List[OpsCommentRead]:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    comments = (await session.scalars(
        select(OpsComment)
        .options(selectinload(OpsComment.author))
        .where(OpsComment.subscriber_request_id == request_id)
        .order_by(OpsComment.created_at.desc())
    )).all()
    from ..services.logic import serialize_ops_comment
    return [serialize_ops_comment(comment) for comment in comments]


@router.post('/subscriber-requests/{request_id}/comments', response_model=OpsCommentRead, status_code=status.HTTP_201_CREATED)
async def create_subscriber_request_comment(
    request_id: UUID,
    body: OpsCommentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = subscriber_dispatch_roles,
) -> OpsCommentRead:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    comment = OpsComment(
        subscriber_request_id=request_id,
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


@router.get('/subscriber-requests/{request_id}/contacts', response_model=List[OpsContactRead])
async def get_subscriber_request_contacts(
    request_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> List[OpsContactRead]:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    contacts = (await session.scalars(
        select(OpsContact).where(OpsContact.subscriber_request_id == request_id).order_by(OpsContact.created_at.desc())
    )).all()
    from ..services.logic import serialize_ops_contact
    return [serialize_ops_contact(contact) for contact in contacts]


@router.post('/subscriber-requests/{request_id}/contacts', response_model=OpsContactRead, status_code=status.HTTP_201_CREATED)
async def create_subscriber_request_contact(
    request_id: UUID,
    body: OpsContactCreate,
    session: AsyncSession = Depends(get_session),
    _: User = subscriber_dispatch_roles,
) -> OpsContactRead:
    request = await session.get(SubscriberRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscriber request not found')
    contact = OpsContact(
        subscriber_request_id=request_id,
        title=body.title,
        full_name=body.full_name,
        phone=body.phone,
        notes=body.notes,
    )
    session.add(contact)
    await session.commit()
    from ..services.logic import serialize_ops_contact
    return serialize_ops_contact(contact)



