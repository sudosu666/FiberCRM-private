from datetime import datetime
from math import ceil
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import (
    ArrivalWindow,
    Building,
    BuildingNote,
    Brigade,
    BrigadeMember,
    Fiber,
    FiberStatus,
    InfraStatus,
    Muffle,
    Message,
    OpsComment,
    OpsContact,
    Panel,
    Port,
    PortStatus,
    ClientConnection,
    StockItem,
    StockTransaction,
    Task,
    TaskReport,
    TaskStatus,
    TaskStep,
    TaskType,
    Tender,
    TenderStatus,
    SubscriberRequest,
    SubscriberRequestStatus,
    User,
    UserRole,
    WorkLog,
    WarehouseRequest,
    WarehouseRequestItem,
)
from ..schemas import (
    BuildingMetrics,
    BrigadeBoardItem,
    BrigadeTaskSummary,
    FieldWorkerRead,
    FieldMetrics,
    NetworkFiberRead,
    NetworkMuffleRead,
    NetworkOverview,
    BuildingNetworkRead,
    BuildingNoteRead,
    BuildingSummaryRead,
    DispatchFilterOption,
    DispatchStatsRead,
    DispatchStatsTaskTypeBreakdown,
    OpsCommentRead,
    OpsContactRead,
    StockItemRead,
    StockTransactionRead,
    SubscriberDispatcherSummary,
    SubscriberRequestRead,
    WorkerStatsRead,
    TaskQueueItem,
    TimelineBlock,
    TimelineHour,
    TenderOverview,
    WorkLogRead,
    WorkSummaryRead,
    WarehouseRequestItemRead,
    WarehouseRequestRead,
)
from ..routers.auth_helpers import user_role_values


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


def serialize_building_note(note: BuildingNote) -> BuildingNoteRead:
    tags = []
    if note.role_tags:
        tags = [UserRole(tag.strip()) for tag in note.role_tags.split(',') if tag.strip()]
    return BuildingNoteRead(
        id=note.id,
        building_id=note.building_id,
        author_id=note.author_id,
        author_name=note.author.name if note.author else None,
        body=note.body,
        role_tags=tags,
        created_at=note.created_at,
    )


def serialize_ops_comment(comment: OpsComment) -> OpsCommentRead:
    tags = []
    if comment.role_tags:
        tags = [UserRole(tag.strip()) for tag in comment.role_tags.split(',') if tag.strip()]
    return OpsCommentRead(
        id=comment.id,
        building_id=comment.building_id,
        task_id=comment.task_id,
        subscriber_request_id=comment.subscriber_request_id,
        author_id=comment.author_id,
        author_name=comment.author.name if comment.author else None,
        comment_type=comment.comment_type,
        body=comment.body,
        role_tags=tags,
        created_at=comment.created_at,
    )


def serialize_ops_contact(contact: OpsContact) -> OpsContactRead:
    return OpsContactRead(
        id=contact.id,
        title=contact.title,
        full_name=contact.full_name,
        phone=contact.phone,
        notes=contact.notes,
        created_at=contact.created_at,
    )


def latest_postpone_comment(comments: list[OpsComment] | None) -> OpsComment | None:
    postpone_comments = [item for item in (comments or []) if item.comment_type == 'postpone']
    if not postpone_comments:
        return None
    return max(postpone_comments, key=lambda item: item.created_at)


def _task_progress_pct(task: Task) -> int:
    if task.status == TaskStatus.completed:
        return 100
    if task.status == TaskStatus.in_progress:
        return 60
    if task.status == TaskStatus.assigned:
        return 35
    return 10


def building_line_usage(building: Building | None) -> tuple[int, int, int]:
    if not building:
        return 0, 0, 0
    connected = 0
    reserved = 0
    for panel in building.panels or []:
        for port in panel.ports or []:
            if port.status == PortStatus.active:
                connected += 1
            elif port.status == PortStatus.reserved:
                reserved += 1
    total_flats = calculate_building_metrics(building).total_flats
    return connected, reserved, max(0, total_flats - connected - reserved)


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
    connected_lines, reserved_lines, unclaimed_lines = building_line_usage(task.building)
    postpone_comment = latest_postpone_comment(getattr(task, "comments", None))
    postponed_at = postpone_comment.created_at if postpone_comment else None
    is_postponed = postpone_comment is not None and task.status == TaskStatus.on_hold
    postponed_over_shift = bool(postponed_at and (datetime.utcnow() - postponed_at).total_seconds() > 8 * 3600)
    return TaskQueueItem(
        id=str(task.id),
        type=task.type,
        status=task.status,
        priority=task.priority,
        description=task.description,
        building_id=str(task.building_id) if task.building_id else None,
        brigade_id=str(task.brigade_id) if task.brigade_id else None,
        building_address=building_address,
        brigade_name=brigade_name,
        estimated_hours=task.estimated_hours,
        is_critical=task.is_critical,
        hold_reason=task.hold_reason,
        started_at=task.started_at,
        ended_at=task.ended_at,
        metrics=metrics,
        connected_lines=connected_lines,
        reserved_lines=reserved_lines,
        unclaimed_lines=unclaimed_lines,
        is_postponed=is_postponed,
        postponed_reason=postpone_comment.body if postpone_comment else None,
        postponed_at=postponed_at,
        postponed_over_shift=postponed_over_shift,
        contacts=[serialize_ops_contact(contact) for contact in sorted(getattr(task, "contacts", []) or [], key=lambda item: item.created_at, reverse=True)],
        comments=[serialize_ops_comment(comment) for comment in sorted(getattr(task, "comments", []) or [], key=lambda item: item.created_at, reverse=True)],
        status_changed_at=task.ended_at or task.completed_at or task.started_at or task.assigned_at or task.created_at,
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
    stmt = select(Task).options(
        selectinload(Task.building).selectinload(Building.panels).selectinload(Panel.ports),
        selectinload(Task.brigade),
        selectinload(Task.contacts),
        selectinload(Task.comments).selectinload(OpsComment.author),
    )
    result = await session.scalars(stmt)
    tasks = result.all()
    return [task_to_queue_item(task) for task in tasks]


async def load_building_summaries(session: AsyncSession) -> List[BuildingSummaryRead]:
    stmt = (
        select(Building)
        .options(
            selectinload(Building.panels).selectinload(Panel.ports),
            selectinload(Building.notes).selectinload(BuildingNote.author),
            selectinload(Building.comments).selectinload(OpsComment.author),
        )
        .order_by(Building.city, Building.address)
    )
    buildings = list((await session.scalars(stmt)).all())
    payload: list[BuildingSummaryRead] = []
    for building in buildings:
        connected_lines, reserved_lines, unclaimed_lines = building_line_usage(building)
        payload.append(BuildingSummaryRead(
            building_id=building.id,
            address=building.address,
            city=building.city,
            servicing_org_name=building.servicing_org_name,
            servicing_org_phone=building.servicing_org_phone,
            infrastructure_status=building.infrastructure_status.value if isinstance(building.infrastructure_status, InfraStatus) else str(building.infrastructure_status),
            metrics=calculate_building_metrics(building),
            connected_lines=connected_lines,
            reserved_lines=reserved_lines,
            unclaimed_lines=unclaimed_lines,
            notes=[serialize_building_note(note) for note in sorted(building.notes or [], key=lambda item: item.created_at, reverse=True)],
            comments=[serialize_ops_comment(comment) for comment in sorted(getattr(building, "comments", []) or [], key=lambda item: item.created_at, reverse=True)],
        ))
    return payload


def serialize_subscriber_request(request: SubscriberRequest) -> SubscriberRequestRead:
    connected_lines, reserved_lines, unclaimed_lines = building_line_usage(request.building)
    postpone_comment = latest_postpone_comment(getattr(request, "comments", None))
    postponed_at = postpone_comment.created_at if postpone_comment else None
    postponed_over_shift = bool(postponed_at and (datetime.utcnow() - postponed_at).total_seconds() > 8 * 3600)
    return SubscriberRequestRead(
        id=request.id,
        building_id=request.building_id,
        building_address=request.building.address if request.building else "—",
        city=request.building.city if request.building else None,
        flat_number=request.flat_number,
        customer_name=request.customer_name,
        phone=request.phone,
        notes=request.notes,
        status=SubscriberRequestStatus(request.status.value if hasattr(request.status, "value") else str(request.status)),
        registered_at=request.registered_at,
        deadline_at=request.deadline_at,
        scheduled_date=request.scheduled_date,
        arrival_window=ArrivalWindow(request.arrival_window.value if request.arrival_window and hasattr(request.arrival_window, "value") else request.arrival_window) if request.arrival_window else None,
        assigned_user_id=request.assigned_user_id,
        assigned_user_name=request.assigned_user.name if request.assigned_user else None,
        is_postponed=postpone_comment is not None and request.status == SubscriberRequestStatus.postponed,
        postponed_reason=postpone_comment.body if postpone_comment else None,
        postponed_at=postponed_at,
        postponed_over_shift=postponed_over_shift,
        connected_lines=connected_lines,
        reserved_lines=reserved_lines,
        unclaimed_lines=unclaimed_lines,
        technical_possible=unclaimed_lines > 0,
        contacts=[serialize_ops_contact(contact) for contact in sorted(getattr(request, "contacts", []) or [], key=lambda item: item.created_at, reverse=True)],
        comments=[serialize_ops_comment(comment) for comment in sorted(getattr(request, "comments", []) or [], key=lambda item: item.created_at, reverse=True)],
    )


async def load_subscriber_requests(session: AsyncSession) -> List[SubscriberRequestRead]:
    stmt = (
        select(SubscriberRequest)
        .options(
            selectinload(SubscriberRequest.building).selectinload(Building.panels).selectinload(Panel.ports),
            selectinload(SubscriberRequest.assigned_user),
            selectinload(SubscriberRequest.contacts),
            selectinload(SubscriberRequest.comments).selectinload(OpsComment.author),
        )
        .order_by(SubscriberRequest.registered_at.desc())
    )
    requests = list((await session.scalars(stmt)).all())
    return [serialize_subscriber_request(item) for item in requests]


async def load_subscriber_dispatch_summary(session: AsyncSession) -> SubscriberDispatcherSummary:
    requests = await load_subscriber_requests(session)
    now = datetime.utcnow()
    return SubscriberDispatcherSummary(
        total_requests=len(requests),
        new_requests=sum(1 for item in requests if item.status == SubscriberRequestStatus.new),
        scheduled_requests=sum(1 for item in requests if item.status == SubscriberRequestStatus.scheduled),
        overdue_requests=sum(1 for item in requests if item.deadline_at < now and item.status not in {SubscriberRequestStatus.completed, SubscriberRequestStatus.canceled}),
        technical_blocked=sum(1 for item in requests if not item.technical_possible),
    )


async def load_dispatch_stats(
    session: AsyncSession,
    *,
    status: str | None = None,
    task_type: str | None = None,
    brigade_id: UUID | None = None,
    city: str | None = None,
    critical_only: bool = False,
    search: str | None = None,
) -> DispatchStatsRead:
    stmt = select(Task).options(selectinload(Task.building), selectinload(Task.brigade))
    tasks = list((await session.scalars(stmt)).all())

    def matches(task: Task) -> bool:
        if status and task.status.value != status:
            return False
        if task_type and task.type.value != task_type:
            return False
        if brigade_id and task.brigade_id != brigade_id:
            return False
        if city and ((task.building.city if task.building else None) or '').lower() != city.lower():
            return False
        if critical_only and not task.is_critical:
            return False
        if search:
            haystack = ' '.join([
                task.description or '',
                task.building.address if task.building else '',
                task.brigade.name if task.brigade else '',
                task.building.city if task.building and task.building.city else '',
            ]).lower()
            if search.lower() not in haystack:
                return False
        return True

    filtered = [task for task in tasks if matches(task)]
    total_tasks = len(filtered)
    estimated = [float(task.estimated_hours or 0.0) for task in filtered]
    type_breakdown: list[DispatchStatsTaskTypeBreakdown] = []
    for current_type in TaskType:
        scoped = [task for task in filtered if task.type == current_type]
        type_breakdown.append(DispatchStatsTaskTypeBreakdown(
            type=current_type,
            total=len(scoped),
            pending=sum(1 for task in scoped if task.status == TaskStatus.pending),
            assigned=sum(1 for task in scoped if task.status == TaskStatus.assigned),
            in_progress=sum(1 for task in scoped if task.status == TaskStatus.in_progress),
            on_hold=sum(1 for task in scoped if task.status == TaskStatus.on_hold),
            completed=sum(1 for task in scoped if task.status == TaskStatus.completed),
        ))

    brigade_options = sorted({
        (str(task.brigade_id), task.brigade.name)
        for task in tasks if task.brigade_id and task.brigade
    }, key=lambda item: item[1])
    city_options = sorted({
        task.building.city.strip()
        for task in tasks if task.building and task.building.city and task.building.city.strip()
    })

    return DispatchStatsRead(
        total_tasks=total_tasks,
        pending_tasks=sum(1 for task in filtered if task.status == TaskStatus.pending),
        assigned_tasks=sum(1 for task in filtered if task.status == TaskStatus.assigned),
        in_progress_tasks=sum(1 for task in filtered if task.status == TaskStatus.in_progress),
        on_hold_tasks=sum(1 for task in filtered if task.status == TaskStatus.on_hold),
        completed_tasks=sum(1 for task in filtered if task.status == TaskStatus.completed),
        critical_tasks=sum(1 for task in filtered if task.is_critical),
        unassigned_tasks=sum(1 for task in filtered if task.brigade_id is None),
        avg_estimated_hours=round((sum(estimated) / total_tasks), 2) if total_tasks else 0.0,
        total_estimated_hours=round(sum(estimated), 2),
        type_breakdown=type_breakdown,
        brigade_options=[DispatchFilterOption(value=value, label=label) for value, label in brigade_options],
        city_options=[DispatchFilterOption(value=value, label=value) for value in city_options],
    )


async def load_brigade_board(session: AsyncSession) -> List[BrigadeBoardItem]:
    stmt = select(Brigade).options(
        selectinload(Brigade.tasks).selectinload(Task.building),
        selectinload(Brigade.members),
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


async def load_field_workers(session: AsyncSession) -> List[FieldWorkerRead]:
    users = (await session.scalars(select(User))).all()
    memberships = (await session.scalars(
        select(BrigadeMember).options(selectinload(BrigadeMember.brigade))
    )).all()
    membership_map: dict[UUID, BrigadeMember] = {member.user_id: member for member in memberships}
    field_roles = {UserRole.Builder, UserRole.Welder, UserRole.Connector}
    workers: list[FieldWorkerRead] = []
    for user in users:
        roles = [UserRole(role) for role in sorted(user_role_values(user))]
        if not any(role in field_roles for role in roles):
            continue
        membership = membership_map.get(user.id)
        brigade = membership.brigade if membership else None
        workers.append(FieldWorkerRead(
            id=user.id,
            name=user.name,
            phone=user.phone,
            role=user.role,
            roles=roles,
            brigade_id=brigade.id if brigade else None,
            brigade_name=brigade.name if brigade else None,
        ))
    workers.sort(key=lambda item: item.name)
    return workers


async def load_worker_stats(
    session: AsyncSession,
    *,
    role: str | None = None,
    brigade_id: UUID | None = None,
    search: str | None = None,
) -> List[WorkerStatsRead]:
    users = (await session.scalars(select(User))).all()
    memberships = (await session.scalars(
        select(BrigadeMember).options(selectinload(BrigadeMember.brigade))
    )).all()
    membership_map: dict[UUID, BrigadeMember] = {member.user_id: member for member in memberships}
    field_roles = {UserRole.Builder, UserRole.Welder, UserRole.Connector}
    task_stmt = select(Task).options(selectinload(Task.brigade))
    tasks = (await session.scalars(task_stmt)).all()
    reports = (await session.scalars(select(TaskReport))).all()
    steps = (await session.scalars(select(TaskStep))).all()
    logs = (await session.scalars(select(WorkLog))).all()

    records: list[WorkerStatsRead] = []
    for user in users:
        user_roles = {UserRole(entry) for entry in sorted(user_role_values(user))}
        if not user_roles.intersection(field_roles):
            continue
        membership = membership_map.get(user.id)
        brigade = membership.brigade if membership else None
        if role and user.role.value != role and role not in {entry.value for entry in user_roles}:
            continue
        if brigade_id and (not brigade or brigade.id != brigade_id):
            continue
        if search and search.lower() not in f"{user.name} {user.phone} {brigade.name if brigade else ''}".lower():
            continue

        user_task_ids = {
            task.id for task in tasks
            if task.brigade_id and brigade and task.brigade_id == brigade.id
        }
        user_logs = [log for log in logs if log.user_id == user.id]
        user_steps = [step for step in steps if step.done_by == user.id]
        user_reports = [report for report in reports if report.user_id == user.id]

        assigned_tasks = sum(1 for task in tasks if task.id in user_task_ids and task.status == TaskStatus.assigned)
        in_progress_tasks = sum(1 for task in tasks if task.id in user_task_ids and task.status == TaskStatus.in_progress)
        completed_tasks = sum(1 for task in tasks if task.id in user_task_ids and task.status == TaskStatus.completed)
        on_hold_events = sum(1 for log in user_logs if log.event_type == 'task.on_hold')

        records.append(WorkerStatsRead(
            user_id=user.id,
            name=user.name,
            phone=user.phone,
            role=user.role,
            brigade_id=brigade.id if brigade else None,
            brigade_name=brigade.name if brigade else None,
            assigned_tasks=assigned_tasks,
            in_progress_tasks=in_progress_tasks,
            completed_tasks=completed_tasks,
            on_hold_events=on_hold_events,
            completed_steps=len(user_steps),
            photo_reports=len(user_reports),
            worklog_entries=len(user_logs),
            total_logged_quantity=round(sum(float(log.quantity or 0) for log in user_logs), 2),
        ))
    records.sort(key=lambda item: (-item.completed_tasks, -item.in_progress_tasks, item.name))
    return records


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
        shortage=item.quantity < item.min_quantity,
    ) for item in items]


async def load_stock_transactions(session: AsyncSession) -> List[StockTransactionRead]:
    stmt = select(StockTransaction).options(
        selectinload(StockTransaction.stock_item),
    ).order_by(StockTransaction.created_at.desc()).limit(100)
    result = await session.scalars(stmt)
    items = result.all()
    return [StockTransactionRead(
        id=item.id,
        stock_item_id=item.stock_item_id,
        stock_item_name=item.stock_item.name if item.stock_item else 'Unknown',
        delta=item.delta,
        reason=item.reason,
        task_id=item.task_id,
        user_id=item.user_id,
        created_at=item.created_at,
    ) for item in items]


async def load_warehouse_requests(session: AsyncSession) -> List[WarehouseRequestRead]:
    stmt = select(WarehouseRequest).options(
        selectinload(WarehouseRequest.building),
        selectinload(WarehouseRequest.items).selectinload(WarehouseRequestItem.stock_item),
    )
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
                id=item.id,
                stock_item_name=item.stock_item.name,
                planned_qty=item.planned_qty,
                fulfilled_qty=item.fulfilled_qty,
            ) for item in req.items],
        ))
    return records


async def load_field_metrics(session: AsyncSession) -> FieldMetrics:
    total_tasks = await session.scalar(select(func.count()).select_from(Task))
    assigned_tasks = await session.scalar(
        select(func.count()).select_from(Task).where(Task.status == TaskStatus.assigned)
    )
    in_progress_tasks = await session.scalar(
        select(func.count()).select_from(Task).where(Task.status == TaskStatus.in_progress)
    )
    completed_tasks = await session.scalar(
        select(func.count()).select_from(Task).where(Task.status == TaskStatus.completed)
    )
    steps_total = await session.scalar(select(func.count()).select_from(TaskStep))
    steps_done = await session.scalar(
        select(func.count()).select_from(TaskStep).where(TaskStep.is_done == True)
    )
    photo_reports = await session.scalar(select(func.count()).select_from(TaskReport))
    worklog_entries = await session.scalar(select(func.count()).select_from(WorkLog))

    msg_stmt = select(Message).options(selectinload(Message.sender)).order_by(Message.created_at.desc()).limit(1)
    recent_message = (await session.execute(msg_stmt)).scalars().first()
    recent_chat = None
    if recent_message:
        sender = recent_message.sender.name if recent_message.sender else 'Поле'
        recent_chat = f"{sender}: {recent_message.body or '…'}"

    recent_report = await session.scalar(
        select(TaskReport).order_by(TaskReport.created_at.desc()).limit(1)
    )
    recent_photo_url = recent_report.photo_url if recent_report else None

    return FieldMetrics(
        total_tasks=total_tasks or 0,
        assigned_tasks=assigned_tasks or 0,
        in_progress_tasks=in_progress_tasks or 0,
        completed_tasks=completed_tasks or 0,
        steps_done=steps_done or 0,
        steps_total=steps_total or 0,
        photo_reports=photo_reports or 0,
        worklog_entries=worklog_entries or 0,
        recent_chat=recent_chat,
        recent_photo_url=recent_photo_url,
    )


async def load_task_work_summary(session: AsyncSession, task_id: UUID) -> Optional[WorkSummaryRead]:
    task = await session.get(Task, task_id)
    if not task:
        return None
    logs = (await session.scalars(
        select(WorkLog).where(WorkLog.task_id == task_id).order_by(WorkLog.event_at.desc(), WorkLog.recorded_at.desc())
    )).all()
    total_quantity = round(sum(log.quantity for log in logs), 2)
    last_event_at = logs[0].event_at if logs else None
    return WorkSummaryRead(
        task_id=task.id,
        entries=len(logs),
        total_quantity=total_quantity,
        last_event_at=last_event_at,
        logs=[
            WorkLogRead(
                id=log.id,
                user_id=log.user_id,
                task_id=log.task_id,
                event_type=log.event_type,
                description=log.description,
                quantity=log.quantity,
                unit=log.unit,
                event_at=log.event_at,
                recorded_at=log.recorded_at,
            )
            for log in logs
        ],
    )


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
    panels = (await session.scalars(select(Panel).where(Panel.building_id == building.id))).all()
    panel_ids = [panel.id for panel in panels]
    ports = (await session.scalars(select(Port).where(Port.panel_id.in_(panel_ids)))).all() if panel_ids else []
    connected_lines = sum(1 for port in ports if port.status == PortStatus.active)
    reserved_lines = sum(1 for port in ports if port.status == PortStatus.reserved)
    unclaimed_lines = max(0, metrics.total_flats - connected_lines - reserved_lines)
    return BuildingNetworkRead(
        id=building.id,
        address=building.address,
        city=building.city,
        servicing_org_name=building.servicing_org_name,
        servicing_org_phone=building.servicing_org_phone,
        metrics=metrics,
        connected_lines=connected_lines,
        reserved_lines=reserved_lines,
        unclaimed_lines=unclaimed_lines,
        comments=[],
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
    return status in {TaskStatus.assigned, TaskStatus.in_progress, TaskStatus.on_hold}
