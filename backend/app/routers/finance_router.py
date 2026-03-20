from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import (
    Brigade,
    BrigadeMember,
    Building,
    SubscriberRequest,
    Task,
    User,
    UserRole,
    WorkEntry,
    WorkRate,
)
from ..schemas import (
    BrigadePayoutRead,
    CalendarEventRead,
    WorkEntryCreate,
    WorkEntryRead,
    WorkRateRead,
    WorkRateUpsert,
)
from .auth_helpers import require_roles

router = APIRouter(prefix="/api")

dispatcher_or_warehouse = Depends(require_roles(UserRole.Dispatcher, UserRole.Warehouse))
ops_roles = Depends(require_roles(UserRole.Dispatcher, UserRole.Builder, UserRole.Welder, UserRole.Connector, UserRole.Warehouse))
field_roles = Depends(require_roles(UserRole.Builder, UserRole.Welder, UserRole.Connector))


def _rate_to_read(rate: WorkRate) -> WorkRateRead:
    return WorkRateRead(
        id=rate.id,
        code=rate.code,
        title=rate.title,
        unit=rate.unit,
        price_uah=float(rate.price_uah or 0.0),
        is_active=bool(rate.is_active),
        updated_at=rate.updated_at,
    )


@router.get("/work-rates", response_model=list[WorkRateRead])
async def list_work_rates(
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> list[WorkRateRead]:
    stmt = select(WorkRate).order_by(WorkRate.title.asc())
    rates = (await session.scalars(stmt)).all()
    if active_only:
        rates = [item for item in rates if item.is_active]
    return [_rate_to_read(rate) for rate in rates]


@router.post("/work-rates", response_model=WorkRateRead, status_code=status.HTTP_201_CREATED)
async def create_work_rate(
    body: WorkRateUpsert,
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_or_warehouse,
) -> WorkRateRead:
    existing = (await session.scalars(select(WorkRate).where(WorkRate.code == body.code).limit(1))).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Work rate code already exists")
    rate = WorkRate(
        code=body.code,
        title=body.title,
        unit=body.unit,
        price_uah=body.price_uah,
        is_active=body.is_active,
        updated_at=datetime.utcnow(),
    )
    session.add(rate)
    await session.commit()
    await session.refresh(rate)
    return _rate_to_read(rate)


@router.patch("/work-rates/{rate_id}", response_model=WorkRateRead)
async def update_work_rate(
    rate_id: UUID,
    body: WorkRateUpsert,
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_or_warehouse,
) -> WorkRateRead:
    rate = await session.get(WorkRate, rate_id)
    if not rate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work rate not found")
    rate.code = body.code
    rate.title = body.title
    rate.unit = body.unit
    rate.price_uah = body.price_uah
    rate.is_active = body.is_active
    rate.updated_at = datetime.utcnow()
    session.add(rate)
    await session.commit()
    await session.refresh(rate)
    return _rate_to_read(rate)


@router.post("/tasks/{task_id}/work-entries", response_model=WorkEntryRead, status_code=status.HTTP_201_CREATED)
async def create_work_entry(
    task_id: UUID,
    body: WorkEntryCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = field_roles,
) -> WorkEntryRead:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    rate = (await session.scalars(
        select(WorkRate).where(WorkRate.code == body.work_code, WorkRate.is_active == True).limit(1)
    )).first()
    if not rate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work rate not found")

    event_at = body.event_at or datetime.utcnow()
    total = round(float(body.quantity) * float(rate.price_uah or 0.0), 2)
    entry = WorkEntry(
        task_id=task.id,
        brigade_id=task.brigade_id,
        user_id=current_user.id,
        work_rate_id=rate.id,
        work_code=rate.code,
        title=rate.title,
        quantity=body.quantity,
        unit=rate.unit,
        unit_price_uah=rate.price_uah,
        total_price_uah=total,
        notes=body.notes,
        event_at=event_at,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return WorkEntryRead(
        id=entry.id,
        task_id=entry.task_id,
        brigade_id=entry.brigade_id,
        user_id=entry.user_id,
        work_rate_id=entry.work_rate_id,
        work_code=entry.work_code,
        title=entry.title,
        quantity=entry.quantity,
        unit=entry.unit,
        unit_price_uah=entry.unit_price_uah,
        total_price_uah=entry.total_price_uah,
        notes=entry.notes,
        event_at=entry.event_at,
        created_at=entry.created_at,
    )


@router.get("/brigades/{brigade_id}/payout", response_model=BrigadePayoutRead)
async def get_brigade_payout(
    brigade_id: UUID,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_or_warehouse,
) -> BrigadePayoutRead:
    brigade = await session.get(Brigade, brigade_id)
    if not brigade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brigade not found")
    end = date_to or datetime.utcnow()
    start = date_from or (end - timedelta(days=30))

    entries = (await session.scalars(
        select(WorkEntry)
        .where(
            WorkEntry.brigade_id == brigade.id,
            WorkEntry.event_at >= start,
            WorkEntry.event_at <= end,
        )
        .order_by(WorkEntry.event_at.asc())
    )).all()
    total_amount = round(sum(float(item.total_price_uah or 0.0) for item in entries), 2)

    members = (await session.scalars(select(BrigadeMember).where(BrigadeMember.brigade_id == brigade.id))).all()
    member_ids = {item.user_id for item in members}
    if brigade.foreman_id:
        member_ids.add(brigade.foreman_id)
    members_count = max(1, len(member_ids))
    per_member = round(total_amount / float(members_count), 2)

    return BrigadePayoutRead(
        brigade_id=brigade.id,
        brigade_name=brigade.name,
        date_from=start,
        date_to=end,
        entries_count=len(entries),
        total_amount_uah=total_amount,
        members_count=members_count,
        per_member_amount_uah=per_member,
        member_user_ids=sorted(member_ids, key=str),
    )


@router.get("/calendar/events", response_model=list[CalendarEventRead])
async def list_calendar_events(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: User = ops_roles,
) -> list[CalendarEventRead]:
    end = date_to or (datetime.utcnow() + timedelta(days=30))
    start = date_from or (datetime.utcnow() - timedelta(days=30))
    events: list[CalendarEventRead] = []

    tasks = (await session.scalars(select(Task).where(Task.created_at >= start, Task.created_at <= end))).all()
    for task in tasks:
        building = await session.get(Building, task.building_id) if task.building_id else None
        brigade = await session.get(Brigade, task.brigade_id) if task.brigade_id else None
        starts_at = task.started_at or task.assigned_at or task.created_at
        ends_at = task.completed_at or task.ended_at
        events.append(CalendarEventRead(
            entity_type="task",
            entity_id=task.id,
            title=f"Task {task.type.value}",
            status=task.status.value,
            starts_at=starts_at,
            ends_at=ends_at,
            building_address=building.address if building else None,
            brigade_name=brigade.name if brigade else None,
        ))

    requests = (await session.scalars(
        select(SubscriberRequest).where(SubscriberRequest.registered_at >= start, SubscriberRequest.registered_at <= end)
    )).all()
    for req in requests:
        building = await session.get(Building, req.building_id) if req.building_id else None
        starts_at = datetime.combine(req.scheduled_date, datetime.min.time()) if req.scheduled_date else req.registered_at
        events.append(CalendarEventRead(
            entity_type="subscriber_request",
            entity_id=req.id,
            title=f"Заявка абонента кв. {req.flat_number}",
            status=req.status.value,
            starts_at=starts_at,
            ends_at=req.completed_at,
            building_address=building.address if building else None,
            brigade_name=None,
        ))

    events.sort(key=lambda item: item.starts_at)
    return events
