from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column,
    DateTime,
    Enum as PgEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    Float,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
import uuid

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

class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    role = Column(PgEnum(UserRole, name='user_role'), default=UserRole.dispatcher, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Tender(Base):
    __tablename__ = 'tenders'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    customer = Column(String(100), nullable=False, default='Vodafone Ukraine')
    status = Column(PgEnum(TenderStatus, name='tender_status'), default=TenderStatus.new)
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

class Building(Base):
    __tablename__ = 'buildings'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tender_id = Column(UUID(as_uuid=True), ForeignKey('tenders.id'))
    address = Column(Text, nullable=False)
    entrances_count = Column(Integer, default=1)
    floors_count = Column(Integer, default=1)
    flats_per_floor = Column(Integer, default=1)
    distance_from_muffle = Column(Float, default=0.0)
    infrastructure_status = Column(String(20), default='planned')

class Muffle(Base):
    __tablename__ = 'muffles'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coordinate_lat = Column(Float, nullable=True)
    coordinate_lon = Column(Float, nullable=True)
    capacity = Column(Integer, default=16)

class Fiber(Base):
    __tablename__ = 'fibers'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    muffle_id = Column(UUID(as_uuid=True), ForeignKey('muffles.id'))
    fiber_number = Column(Integer, nullable=False)
    status = Column(String(20), default='free')
    connected_building_id = Column(UUID(as_uuid=True), ForeignKey('buildings.id'), nullable=True)

class Brigade(Base):
    __tablename__ = 'brigades'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(80), nullable=False)
    role = Column(String(32), nullable=False)
    members = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

class Task(Base):
    __tablename__ = 'tasks'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(PgEnum(TaskType, name='task_type'), nullable=False)
    status = Column(PgEnum(TaskStatus, name='task_status'), default=TaskStatus.pending)
    building_id = Column(UUID(as_uuid=True), ForeignKey('buildings.id'))
    brigade_id = Column(UUID(as_uuid=True), ForeignKey('brigades.id'), nullable=True)
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
