from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlmodel import Field, Relationship, SQLModel


class UserRole(str, Enum):
    Designer = "Designer"
    Dispatcher = "Dispatcher"
    ConnectionDispatcher = "ConnectionDispatcher"
    Builder = "Builder"
    Welder = "Welder"
    Connector = "Connector"
    Warehouse = "Warehouse"


class TenderStatus(str, Enum):
    new = "new"
    planning = "planning"
    in_progress = "in_progress"
    completed = "completed"


class TaskType(str, Enum):
    construction = "construction"
    welding = "welding"
    connection = "connection"


class TaskStatus(str, Enum):
    pending = "pending"
    assigned = "assigned"
    in_progress = "in_progress"
    on_hold = "on_hold"
    completed = "completed"
    canceled = "canceled"


class FiberStatus(str, Enum):
    free = "free"
    reserved = "reserved"
    busy = "busy"


class PortStatus(str, Enum):
    free = "free"
    reserved = "reserved"
    active = "active"
    faulty = "faulty"


class InfraStatus(str, Enum):
    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"


class RequestStatus(str, Enum):
    pending = "pending"
    fulfilled = "fulfilled"
    partial = "partial"
    rejected = "rejected"


class SubscriberRequestStatus(str, Enum):
    new = "new"
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    postponed = "postponed"
    canceled = "canceled"
    no_access = "no_access"
    technical_issue = "technical_issue"


class ArrivalWindow(str, Enum):
    before_lunch = "before_lunch"
    after_lunch = "after_lunch"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(nullable=False)
    phone: str = Field(sa_column=Column(String(20), unique=True, nullable=False))
    email: Optional[str] = Field(default=None, sa_column=Column(String(150), unique=True))
    role: UserRole = Field(sa_column=Column(PgEnum(UserRole, name="user_role")), default=UserRole.Dispatcher)
    additional_roles: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    password_hash: str = Field(sa_column=Column(Text, nullable=False))
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    led_brigades: list["Brigade"] = Relationship(back_populates="foreman")
    memberships: list["BrigadeMember"] = Relationship(back_populates="user")
    task_steps_done: list["TaskStep"] = Relationship(back_populates="actor")
    task_reports: list["TaskReport"] = Relationship(back_populates="user")
    notifications: list["Notification"] = Relationship(back_populates="user")
    push_subscriptions: list["PushSubscription"] = Relationship(back_populates="user")
    stock_transactions: list["StockTransaction"] = Relationship(back_populates="user")
    work_logs: list["WorkLog"] = Relationship(back_populates="user")


class Brigade(SQLModel, table=True):
    __tablename__ = "brigades"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(nullable=False)
    type: TaskType = Field(sa_column=Column(PgEnum(TaskType, name="task_type"), nullable=False))
    foreman_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    is_active: bool = Field(default=True)

    foreman: Optional[User] = Relationship(back_populates="led_brigades")
    tasks: list["Task"] = Relationship(back_populates="brigade")
    members: list["BrigadeMember"] = Relationship(back_populates="brigade")


class BrigadeMember(SQLModel, table=True):
    __tablename__ = "brigade_members"

    brigade_id: UUID = Field(foreign_key="brigades.id", primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", primary_key=True)

    brigade: Brigade = Relationship(back_populates="members")
    user: User = Relationship(back_populates="memberships")


class Tender(SQLModel, table=True):
    __tablename__ = "tenders"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(nullable=False)
    customer: str = Field(default="Vodafone Ukraine")
    city: Optional[str] = None
    status: TenderStatus = Field(sa_column=Column(PgEnum(TenderStatus, name="tender_status")), default=TenderStatus.new)
    deadline: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None

    buildings: list["Building"] = Relationship(back_populates="tender")


class Building(SQLModel, table=True):
    __tablename__ = "buildings"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tender_id: UUID = Field(foreign_key="tenders.id")
    address: str = Field(nullable=False)
    city: Optional[str] = None
    servicing_org_name: Optional[str] = None
    servicing_org_phone: Optional[str] = Field(default=None, sa_column=Column(String(100), nullable=True))
    entrances_count: int = Field(nullable=False)
    floors_count: int = Field(nullable=False)
    flats_per_floor: int = Field(nullable=False)
    floor_height_m: float = Field(default=2.8)
    panel_every_n_floors: int = Field(default=5)
    distance_from_muffle_m: Optional[float] = None
    cable_reserve_pct: int = Field(default=15)
    cable_entry_point: Optional[str] = None
    cable_entry_notes: Optional[str] = None
    planned_cable_meters: Optional[float] = None
    actual_cable_meters: Optional[float] = None
    infrastructure_status: InfraStatus = Field(sa_column=Column(PgEnum(InfraStatus, name="infra_status")), default=InfraStatus.planned)
    completed_at: Optional[datetime] = None

    tender: Tender = Relationship(back_populates="buildings")
    tasks: list["Task"] = Relationship(back_populates="building")
    panels: list["Panel"] = Relationship(back_populates="building")
    notes: list["BuildingNote"] = Relationship(back_populates="building", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    subscriber_requests: list["SubscriberRequest"] = Relationship(back_populates="building", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    comments: list["OpsComment"] = Relationship(back_populates="building", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class Muffle(SQLModel, table=True):
    __tablename__ = "muffles"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: Optional[str] = None
    address_note: Optional[str] = None
    coordinate_lat: Optional[float] = None
    coordinate_lon: Optional[float] = None
    capacity: int = Field(default=16)

    fibers: list["Fiber"] = Relationship(back_populates="muffle")


class Fiber(SQLModel, table=True):
    __tablename__ = "fibers"
    __table_args__ = (UniqueConstraint("muffle_id", "fiber_number", name="uq_fibers_number"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    muffle_id: UUID = Field(foreign_key="muffles.id")
    fiber_number: int = Field(nullable=False)
    status: FiberStatus = Field(sa_column=Column(PgEnum(FiberStatus, name="fiber_status")), default=FiberStatus.free)

    muffle: Muffle = Relationship(back_populates="fibers")
    panels: list["Panel"] = Relationship(back_populates="fiber")


class Panel(SQLModel, table=True):
    __tablename__ = "panels"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    building_id: UUID = Field(foreign_key="buildings.id")
    fiber_id: Optional[UUID] = Field(default=None, foreign_key="fibers.id")
    entrance_num: int = Field(nullable=False)
    floor_num: int = Field(nullable=False)
    label: Optional[str] = None
    splitter_ratio: int = Field(default=32)
    installed_at: Optional[datetime] = None

    building: Building = Relationship(back_populates="panels")
    fiber: Optional[Fiber] = Relationship(back_populates="panels")
    ports: list["Port"] = Relationship(back_populates="panel")


class Port(SQLModel, table=True):
    __tablename__ = "ports"
    __table_args__ = (UniqueConstraint("panel_id", "port_number", name="uq_ports_number"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    panel_id: UUID = Field(foreign_key="panels.id")
    port_number: int = Field(nullable=False)
    status: PortStatus = Field(sa_column=Column(PgEnum(PortStatus, name="port_status")), default=PortStatus.free)

    panel: Panel = Relationship(back_populates="ports")


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    type: TaskType = Field(sa_column=Column(PgEnum(TaskType, name="task_type"), nullable=False))
    status: TaskStatus = Field(sa_column=Column(PgEnum(TaskStatus, name="task_status")), default=TaskStatus.pending)
    priority: int = Field(default=0)
    building_id: Optional[UUID] = Field(default=None, foreign_key="buildings.id")
    brigade_id: Optional[UUID] = Field(default=None, foreign_key="brigades.id")
    description: Optional[str] = None
    estimated_hours: Optional[float] = None
    is_critical: bool = Field(default=False)
    hold_reason: Optional[str] = None
    postponed_reason: Optional[str] = None
    postponed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    building: Optional[Building] = Relationship(back_populates="tasks")
    brigade: Optional[Brigade] = Relationship(back_populates="tasks")
    steps: list["TaskStep"] = Relationship(back_populates="task", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    reports: list["TaskReport"] = Relationship(back_populates="task", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    contacts: list["OpsContact"] = Relationship(back_populates="task", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    comments: list["OpsComment"] = Relationship(back_populates="task", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class TaskStep(SQLModel, table=True):
    __tablename__ = "task_steps"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_id: UUID = Field(foreign_key="tasks.id", nullable=False)
    step_order: int = Field(nullable=False)
    title: str = Field(nullable=False)
    hint: Optional[str] = None
    is_done: bool = Field(default=False)
    done_at: Optional[datetime] = None
    done_by: Optional[UUID] = Field(default=None, foreign_key="users.id")

    task: Task = Relationship(back_populates="steps")
    actor: Optional[User] = Relationship(back_populates="task_steps_done")


class TaskReport(SQLModel, table=True):
    __tablename__ = "task_reports"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_id: UUID = Field(foreign_key="tasks.id", nullable=False)
    user_id: UUID = Field(foreign_key="users.id", nullable=False)
    photo_url: Optional[str] = None
    comment: Optional[str] = None
    brigade_id: Optional[UUID] = Field(default=None, foreign_key="brigades.id")
    brigade_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    task: Task = Relationship(back_populates="reports")
    user: User = Relationship(back_populates="task_reports")
    brigade: Optional[Brigade] = Relationship()


class StockItem(SQLModel, table=True):
    __tablename__ = "stock_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(nullable=False)
    unit: str = Field(nullable=False)
    quantity: float = Field(default=0.0)
    min_quantity: float = Field(default=0.0)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    transactions: list["StockTransaction"] = Relationship(back_populates="stock_item")


class StockTransaction(SQLModel, table=True):
    __tablename__ = "stock_transactions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    stock_item_id: UUID = Field(foreign_key="stock_items.id", nullable=False)
    delta: float = Field(nullable=False)
    reason: Optional[str] = None
    task_id: Optional[UUID] = Field(default=None, foreign_key="tasks.id")
    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    stock_item: StockItem = Relationship(back_populates="transactions")
    task: Optional[Task] = Relationship()
    user: Optional[User] = Relationship(back_populates="stock_transactions")


class WarehouseRequest(SQLModel, table=True):
    __tablename__ = "warehouse_requests"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    requested_by: UUID = Field(foreign_key="users.id", nullable=False)
    task_id: Optional[UUID] = Field(default=None, foreign_key="tasks.id")
    building_id: Optional[UUID] = Field(default=None, foreign_key="buildings.id")
    status: RequestStatus = Field(sa_column=Column(PgEnum(RequestStatus, name="request_status")), default=RequestStatus.pending)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    fulfilled_at: Optional[datetime] = None

    items: list["WarehouseRequestItem"] = Relationship(back_populates="request", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    building: Optional[Building] = Relationship(back_populates="comments")


class WarehouseRequestItem(SQLModel, table=True):
    __tablename__ = "warehouse_request_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    request_id: UUID = Field(foreign_key="warehouse_requests.id", nullable=False)
    stock_item_id: UUID = Field(foreign_key="stock_items.id", nullable=False)
    planned_qty: float = Field(nullable=False)
    fulfilled_qty: Optional[float] = None

    request: WarehouseRequest = Relationship(back_populates="items")
    stock_item: StockItem = Relationship()


class ClientConnection(SQLModel, table=True):
    __tablename__ = "client_connections"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    port_id: UUID = Field(foreign_key="ports.id", nullable=False)
    full_name: Optional[str] = None
    flat_number: Optional[int] = None
    phone: Optional[str] = None
    status: str = Field(default="pending")
    connected_at: Optional[datetime] = None
    task_id: Optional[UUID] = Field(default=None, foreign_key="tasks.id")

    port: Port = Relationship()
    task: Optional[Task] = Relationship()


class SubscriberRequest(SQLModel, table=True):
    __tablename__ = "subscriber_requests"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    building_id: UUID = Field(foreign_key="buildings.id", nullable=False)
    flat_number: int = Field(nullable=False)
    customer_name: str = Field(nullable=False)
    phone: str = Field(sa_column=Column(String(20), nullable=False))
    notes: Optional[str] = None
    postponed_reason: Optional[str] = None
    postponed_at: Optional[datetime] = None
    status: SubscriberRequestStatus = Field(
        sa_column=Column(PgEnum(SubscriberRequestStatus, name="subscriber_request_status")),
        default=SubscriberRequestStatus.new,
    )
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    deadline_at: datetime = Field(sa_column=Column(DateTime, nullable=False))
    scheduled_date: Optional[date] = Field(default=None, sa_column=Column(Date, nullable=True))
    arrival_window: Optional[ArrivalWindow] = Field(
        default=None,
        sa_column=Column(PgEnum(ArrivalWindow, name="arrival_window"), nullable=True),
    )
    assigned_user_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    completed_at: Optional[datetime] = None

    building: Building = Relationship(back_populates="subscriber_requests")
    assigned_user: Optional[User] = Relationship()
    contacts: list["OpsContact"] = Relationship(back_populates="subscriber_request", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    comments: list["OpsComment"] = Relationship(back_populates="subscriber_request", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class OpsContact(SQLModel, table=True):
    __tablename__ = "ops_contacts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_id: Optional[UUID] = Field(default=None, foreign_key="tasks.id")
    subscriber_request_id: Optional[UUID] = Field(default=None, foreign_key="subscriber_requests.id")
    title: str = Field(nullable=False)
    full_name: Optional[str] = None
    phone: str = Field(sa_column=Column(String(50), nullable=False))
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    task: Optional[Task] = Relationship(back_populates="contacts")
    subscriber_request: Optional[SubscriberRequest] = Relationship(back_populates="contacts")


class OpsComment(SQLModel, table=True):
    __tablename__ = "ops_comments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    building_id: Optional[UUID] = Field(default=None, foreign_key="buildings.id")
    task_id: Optional[UUID] = Field(default=None, foreign_key="tasks.id")
    subscriber_request_id: Optional[UUID] = Field(default=None, foreign_key="subscriber_requests.id")
    author_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    comment_type: str = Field(default="note", sa_column=Column(String(50), nullable=False))
    body: str = Field(nullable=False)
    role_tags: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    building: Optional[Building] = Relationship()
    task: Optional[Task] = Relationship(back_populates="comments")
    subscriber_request: Optional[SubscriberRequest] = Relationship(back_populates="comments")
    author: Optional[User] = Relationship()


class BuildingNote(SQLModel, table=True):
    __tablename__ = "building_notes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    building_id: UUID = Field(foreign_key="buildings.id", nullable=False)
    author_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    body: str = Field(nullable=False)
    role_tags: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    building: Building = Relationship(back_populates="notes")
    author: Optional[User] = Relationship()


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_id: UUID = Field(foreign_key="tasks.id", nullable=False)
    sender_id: UUID = Field(foreign_key="users.id", nullable=False)
    body: Optional[str] = None
    photo_url: Optional[str] = None
    is_read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    task: Task = Relationship()
    sender: User = Relationship()


class WorkLog(SQLModel, table=True):
    __tablename__ = "work_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    task_id: Optional[UUID] = Field(default=None, foreign_key="tasks.id")
    event_type: str = Field(sa_column=Column(String(50), nullable=False))
    description: Optional[str] = None
    quantity: float = Field(default=1.0)
    unit: str = Field(default="event")
    event_at: datetime = Field(default_factory=datetime.utcnow)
    recorded_at: datetime = Field(default_factory=datetime.utcnow)

    user: Optional[User] = Relationship(back_populates="work_logs")
    task: Optional[Task] = Relationship()


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", nullable=False)
    title: str = Field(nullable=False)
    body: Optional[str] = None
    is_read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    user: User = Relationship(back_populates="notifications")


class PushSubscription(SQLModel, table=True):
    __tablename__ = "push_subscriptions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", nullable=False)
    endpoint: str = Field(nullable=False)
    p256dh: str = Field(nullable=False)
    auth: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    user: User = Relationship(back_populates="push_subscriptions")
