from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as PgEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .database import Base

class UserRole(str, Enum):
    designer = 'Designer'
    dispatcher = 'Dispatcher'
    builder = 'Builder'
    welder = 'Welder'
    connector = 'Connector'
    warehouse = 'Warehouse'

class TenderStatus(str, Enum):
    new = 'new'
    planning = 'planning'
    in_progress = 'in_progress'
    completed = 'completed'

class TaskType(str, Enum):
    construction = 'construction'
    welding = 'welding'
    connection = 'connection'

class TaskStatus(str, Enum):
    pending = 'pending'
    assigned = 'assigned'
    in_progress = 'in_progress'
    completed = 'completed'
    canceled = 'canceled'

class FiberStatus(str, Enum):
    free = 'free'
    reserved = 'reserved'
    busy = 'busy'

class PortStatus(str, Enum):
    free = 'free'
    reserved = 'reserved'
    active = 'active'
    faulty = 'faulty'

class InfraStatus(str, Enum):
    planned = 'planned'
    in_progress = 'in_progress'
    completed = 'completed'

class RequestStatus(str, Enum):
    pending = 'pending'
    fulfilled = 'fulfilled'
    partial = 'partial'
    rejected = 'rejected'


class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(150), nullable=False)
    phone = Column(String(20), unique=True)
    email = Column(String(150), unique=True)
    role = Column(PgEnum(UserRole, name='user_role'), nullable=False, default=UserRole.dispatcher)
    password_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    brigades = relationship('Brigade', back_populates='foreman')


class Brigade(Base):
    __tablename__ = 'brigades'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(100), nullable=False)
    type = Column(PgEnum(TaskType, name='task_type'), nullable=False)
    foreman_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    is_active = Column(Boolean, default=True)

    foreman = relationship('User', back_populates='brigades')
    tasks = relationship('Task', back_populates='brigade')
    members = relationship('BrigadeMember', back_populates='brigade')


class BrigadeMember(Base):
    __tablename__ = 'brigade_members'

    brigade_id = Column(UUID(as_uuid=True), ForeignKey('brigades.id', ondelete='CASCADE'), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)

    brigade = relationship('Brigade', back_populates='members')
    user = relationship('User')


class Tender(Base):
    __tablename__ = 'tenders'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    customer = Column(String(100), nullable=False, default='Vodafone Ukraine')
    city = Column(String(100))
    status = Column(PgEnum(TenderStatus, name='tender_status'), default=TenderStatus.new)
    deadline = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    buildings = relationship('Building', back_populates='tender')


class Building(Base):
    __tablename__ = 'buildings'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tender_id = Column(UUID(as_uuid=True), ForeignKey('tenders.id', ondelete='CASCADE'))
    address = Column(Text, nullable=False)
    city = Column(String(100))
    entrances_count = Column(Integer, nullable=False, default=1)
    floors_count = Column(Integer, nullable=False, default=1)
    flats_per_floor = Column(Integer, nullable=False, default=1)
    floor_height_m = Column(Float, default=2.8)
    panel_every_n_floors = Column(Integer, default=5)
    distance_from_muffle_m = Column(Float, default=0.0)
    cable_reserve_pct = Column(Integer, default=15)
    cable_entry_point = Column(String(150))
    cable_entry_notes = Column(Text)
    planned_cable_meters = Column(Float)
    actual_cable_meters = Column(Float)
    infrastructure_status = Column(PgEnum(InfraStatus, name='infra_status'), default=InfraStatus.planned)
    completed_at = Column(DateTime, nullable=True)

    tender = relationship('Tender', back_populates='buildings')
    tasks = relationship('Task', back_populates='building')
    panels = relationship('Panel', back_populates='building')


class Muffle(Base):
    __tablename__ = 'muffles'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(100))
    address_note = Column(Text)
    coordinate_lat = Column(Float)
    coordinate_lon = Column(Float)
    capacity = Column(Integer, default=16)

    fibers = relationship('Fiber', back_populates='muffle')


class Fiber(Base):
    __tablename__ = 'fibers'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    muffle_id = Column(UUID(as_uuid=True), ForeignKey('muffles.id', ondelete='CASCADE'))
    fiber_number = Column(Integer, nullable=False)
    status = Column(PgEnum(FiberStatus, name='fiber_status'), default=FiberStatus.free)

    muffle = relationship('Muffle', back_populates='fibers')
    panels = relationship('Panel', back_populates='fiber')


class Panel(Base):
    __tablename__ = 'panels'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    building_id = Column(UUID(as_uuid=True), ForeignKey('buildings.id', ondelete='CASCADE'))
    fiber_id = Column(UUID(as_uuid=True), ForeignKey('fibers.id'))
    entrance_num = Column(Integer, nullable=False)
    floor_num = Column(Integer, nullable=False)
    label = Column(String(50))
    splitter_ratio = Column(Integer, default=32)
    installed_at = Column(DateTime)

    building = relationship('Building', back_populates='panels')
    fiber = relationship('Fiber', back_populates='panels')
    ports = relationship('Port', back_populates='panel')


class Port(Base):
    __tablename__ = 'ports'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    panel_id = Column(UUID(as_uuid=True), ForeignKey('panels.id', ondelete='CASCADE'))
    port_number = Column(Integer, nullable=False)
    status = Column(PgEnum(PortStatus, name='port_status'), default=PortStatus.free)

    panel = relationship('Panel', back_populates='ports')


class Task(Base):
    __tablename__ = 'tasks'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    type = Column(PgEnum(TaskType, name='task_type'), nullable=False)
    status = Column(PgEnum(TaskStatus, name='task_status'), default=TaskStatus.pending)
    priority = Column(Integer, default=0)
    building_id = Column(UUID(as_uuid=True), ForeignKey('buildings.id'))
    brigade_id = Column(UUID(as_uuid=True), ForeignKey('brigades.id'))
    description = Column(Text)
    estimated_hours = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    assigned_at = Column(DateTime)
    completed_at = Column(DateTime)

    building = relationship('Building', back_populates='tasks')
    brigade = relationship('Brigade', back_populates='tasks')
    steps = relationship('TaskStep', back_populates='task', cascade='all, delete-orphan')
    reports = relationship('TaskReport', back_populates='task', cascade='all, delete-orphan')


class TaskStep(Base):
    __tablename__ = 'task_steps'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.id', ondelete='CASCADE'))
    step_order = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    hint = Column(Text)
    is_done = Column(Boolean, default=False)
    done_at = Column(DateTime)
    done_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    task = relationship('Task', back_populates='steps')
    actor = relationship('User')


class TaskReport(Base):
    __tablename__ = 'task_reports'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.id', ondelete='CASCADE'))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    photo_url = Column(Text)
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship('Task', back_populates='reports')
    user = relationship('User')


class StockItem(Base):
    __tablename__ = 'stock_items'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(150), nullable=False)
    unit = Column(String(20), nullable=False)
    quantity = Column(Float, default=0.0)
    min_quantity = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship('StockTransaction', back_populates='stock_item')


class StockTransaction(Base):
    __tablename__ = 'stock_transactions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    stock_item_id = Column(UUID(as_uuid=True), ForeignKey('stock_items.id'))
    delta = Column(Float, nullable=False)
    reason = Column(String(100))
    task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.id'))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

    stock_item = relationship('StockItem', back_populates='transactions')


class WarehouseRequest(Base):
    __tablename__ = 'warehouse_requests'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    requested_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.id'))
    building_id = Column(UUID(as_uuid=True), ForeignKey('buildings.id'))
    status = Column(PgEnum(RequestStatus, name='request_status'), default=RequestStatus.pending)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    fulfilled_at = Column(DateTime)

    items = relationship('WarehouseRequestItem', back_populates='request', cascade='all, delete-orphan')
    building = relationship('Building')


class WarehouseRequestItem(Base):
    __tablename__ = 'warehouse_request_items'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey('warehouse_requests.id', ondelete='CASCADE'))
    stock_item_id = Column(UUID(as_uuid=True), ForeignKey('stock_items.id'))
    planned_qty = Column(Float, nullable=False)
    fulfilled_qty = Column(Float)

    request = relationship('WarehouseRequest', back_populates='items')
    stock_item = relationship('StockItem')


class Message(Base):
    __tablename__ = 'messages'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.id', ondelete='CASCADE'))
    sender_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    body = Column(Text)
    photo_url = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    title = Column(String(200), nullable=False)
    body = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PushSubscription(Base):
    __tablename__ = 'push_subscriptions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    endpoint = Column(Text, nullable=False)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
