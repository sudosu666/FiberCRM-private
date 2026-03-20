from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    Designer = 'Designer'
    Dispatcher = 'Dispatcher'
    ConnectionDispatcher = 'ConnectionDispatcher'
    Builder = 'Builder'
    Welder = 'Welder'
    Connector = 'Connector'
    Warehouse = 'Warehouse'


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
    on_hold = 'on_hold'
    completed = 'completed'
    canceled = 'canceled'


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class LoginRequest(BaseModel):
    phone: str
    password: str


class TokenData(BaseModel):
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    roles: List[UserRole] = Field(default_factory=list)


class UserCreate(BaseModel):
    name: str
    phone: str
    password: str
    email: Optional[str] = None
    role: UserRole = UserRole.Dispatcher
    additional_roles: List[UserRole] = Field(default_factory=list)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    phone: str
    email: Optional[str]
    role: UserRole
    roles: List[UserRole] = Field(default_factory=list)
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: UserRole
    additional_roles: List[UserRole] = Field(default_factory=list)
    is_active: bool = True


class TaskBase(BaseModel):
    type: TaskType
    building_id: Optional[UUID]
    brigade_id: Optional[UUID]
    priority: int = Field(0, ge=0)


class TaskRead(TaskBase):
    id: UUID
    status: TaskStatus
    is_critical: bool = False
    hold_reason: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    completed_at: Optional[datetime]


class TaskStepRead(BaseModel):
    id: UUID
    task_id: UUID
    step_order: int
    title: str
    hint: Optional[str]
    is_done: bool
    done_at: Optional[datetime]


class TaskStepCompleteRead(BaseModel):
    task_id: UUID
    step_id: UUID
    is_done: bool
    done_at: Optional[datetime]
    event_at: Optional[datetime]


class TaskReportCreate(BaseModel):
    photo_filename: str
    photo_data: str
    comment: Optional[str] = None
    brigade_id: Optional[UUID] = None
    brigade_name: Optional[str] = None


class TaskReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    user_id: Optional[UUID]
    brigade_id: Optional[UUID]
    brigade_name: Optional[str]
    photo_url: str
    comment: Optional[str]
    created_at: datetime
    event_at: datetime


class FieldMetrics(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_tasks: int
    assigned_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    steps_done: int
    steps_total: int
    photo_reports: int
    worklog_entries: int
    recent_chat: Optional[str]
    recent_photo_url: Optional[str]


class TenderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: TenderStatus
    customer: str
    created_at: datetime


class TenderOverview(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: TenderStatus
    customer: str
    city: Optional[str]
    building_count: int
    task_count: int
    completed_tasks: int
    in_progress_tasks: int
    pending_tasks: int
    planned_cable_meters: float


class TenderCreate(BaseModel):
    name: str
    customer: str = "Vodafone Ukraine"
    city: Optional[str] = None
    deadline: Optional[date] = None


class TenderStatusUpdate(BaseModel):
    status: TenderStatus


class TenderDashboardRead(BaseModel):
    tender_id: UUID
    progress_pct: float
    building_count: int
    task_count: int
    completed_tasks: int
    in_progress_tasks: int
    pending_tasks: int
    active_brigades: int
    planned_cable_meters: float


class TenderCompleteRead(BaseModel):
    tender_id: UUID
    status: TenderStatus
    completed_at: datetime
    handover_summary: str
    blockers: List[str] = Field(default_factory=list)


class BuildingMetrics(BaseModel):
    planned_cable_meters: float
    panels_count: int
    total_flats: int
    distance_from_muffle: float
    cable_reserve_pct: int


class TaskQueueItem(BaseModel):
    id: UUID
    type: TaskType
    status: TaskStatus
    priority: int
    description: Optional[str]
    building_id: Optional[UUID]
    brigade_id: Optional[UUID]
    building_address: Optional[str]
    brigade_name: Optional[str]
    estimated_hours: Optional[float]
    is_critical: bool = False
    hold_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    metrics: BuildingMetrics
    connected_lines: int = 0
    reserved_lines: int = 0
    unclaimed_lines: int = 0
    is_postponed: bool = False
    postponed_reason: Optional[str] = None
    postponed_at: Optional[datetime] = None
    postponed_over_shift: bool = False
    contacts: List["OpsContactRead"] = Field(default_factory=list)
    comments: List["OpsCommentRead"] = Field(default_factory=list)
    status_changed_at: Optional[datetime] = None


class TaskAssignRequest(BaseModel):
    brigade_id: UUID


class TaskStatusEventRead(BaseModel):
    task_id: UUID
    status: TaskStatus
    event_at: datetime
    hold_reason: Optional[str] = None
    is_critical: bool = False


class TaskHoldRequest(BaseModel):
    reason: str = Field(min_length=3)
    is_critical: bool = False


class TaskPostponeRequest(BaseModel):
    reason: str = Field(min_length=3)


class WorkLogRead(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    task_id: Optional[UUID]
    event_type: str
    description: Optional[str]
    quantity: float
    unit: str
    event_at: datetime
    recorded_at: datetime


class WorkSummaryRead(BaseModel):
    task_id: UUID
    entries: int
    total_quantity: float
    last_event_at: Optional[datetime]
    logs: List[WorkLogRead]


class BrigadeTaskSummary(BaseModel):
    id: UUID
    type: TaskType
    status: TaskStatus
    priority: int
    building_address: Optional[str]
    progress_pct: int


class BrigadeBoardItem(BaseModel):
    id: UUID
    name: str
    type: TaskType
    members: int
    is_active: bool
    tasks: List[BrigadeTaskSummary]
    status_label: str


class FieldWorkerRead(BaseModel):
    id: UUID
    name: str
    phone: str
    role: UserRole
    roles: List[UserRole] = Field(default_factory=list)
    brigade_id: Optional[UUID] = None
    brigade_name: Optional[str] = None


class BrigadeUpsert(BaseModel):
    name: str
    type: TaskType
    foreman_id: Optional[UUID] = None
    member_ids: List[UUID] = Field(default_factory=list)
    is_active: bool = True


class TimelineBlock(BaseModel):
    label: str
    duration_hours: float


class TimelineHour(BaseModel):
    hour: int
    blocks: List[TimelineBlock]


class StockItemRead(BaseModel):
    id: UUID
    name: str
    unit: str
    quantity: float
    min_quantity: float
    shortage: bool


class StockAdjustRequest(BaseModel):
    stock_item_id: UUID
    delta: float
    reason: str = Field(min_length=2)


class StockTransactionRead(BaseModel):
    id: UUID
    stock_item_id: UUID
    stock_item_name: str
    delta: float
    reason: Optional[str]
    task_id: Optional[UUID]
    user_id: Optional[UUID]
    created_at: datetime


class WarehouseRequestItemRead(BaseModel):
    id: UUID
    stock_item_name: str
    planned_qty: float
    fulfilled_qty: Optional[float]


class WarehouseRequestRead(BaseModel):
    id: UUID
    building_address: Optional[str]
    status: str
    notes: Optional[str]
    created_at: datetime
    items: List[WarehouseRequestItemRead]


class WarehouseRequestFulfillItem(BaseModel):
    item_id: UUID
    fulfilled_qty: float = Field(gt=0)


class WarehouseRequestFulfill(BaseModel):
    items: List[WarehouseRequestFulfillItem] = Field(default_factory=list)


class WarehouseRequestCreateItem(BaseModel):
    stock_item_id: UUID
    planned_qty: float = Field(gt=0)


class WarehouseRequestCreate(BaseModel):
    building_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    notes: Optional[str] = None
    items: List[WarehouseRequestCreateItem] = Field(default_factory=list)


class NetworkFiberRead(BaseModel):
    id: UUID
    fiber_number: int
    status: str


class NetworkMuffleRead(BaseModel):
    id: UUID
    name: Optional[str]
    address_note: Optional[str]
    coordinate_lat: Optional[float] = None
    coordinate_lon: Optional[float] = None
    capacity: int
    fibers: List[NetworkFiberRead]


class NetworkOverview(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_fibers: int
    reserved_fibers: int
    busy_fibers: int
    total_ports: int
    reserved_ports: int
    active_ports: int
    faulty_ports: int


class BuildingNetworkRead(BaseModel):
    id: UUID
    address: str
    city: Optional[str] = None
    servicing_org_name: Optional[str] = None
    servicing_org_phone: Optional[str] = None
    metrics: BuildingMetrics
    connected_lines: int = 0
    reserved_lines: int = 0
    unclaimed_lines: int = 0
    comments: List["OpsCommentRead"] = Field(default_factory=list)


class BuildingNoteCreate(BaseModel):
    body: str = Field(min_length=1)
    role_tags: List[UserRole] = Field(default_factory=list)


class BuildingNoteRead(BaseModel):
    id: UUID
    building_id: UUID
    author_id: Optional[UUID]
    author_name: Optional[str]
    body: str
    role_tags: List[UserRole] = Field(default_factory=list)
    created_at: datetime


class OpsCommentCreate(BaseModel):
    body: str = Field(min_length=1)
    comment_type: str = Field(default='note', min_length=2)
    role_tags: List[UserRole] = Field(default_factory=list)


class OpsCommentRead(BaseModel):
    id: UUID
    building_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    subscriber_request_id: Optional[UUID] = None
    author_id: Optional[UUID] = None
    author_name: Optional[str] = None
    comment_type: str
    body: str
    role_tags: List[UserRole] = Field(default_factory=list)
    created_at: datetime


class BuildingCalculateRead(BaseModel):
    building_id: UUID
    metrics: BuildingMetrics
    patches_needed: int
    muffles_needed: int
    potential_clients: int


class MuffleCapacityFiberRead(BaseModel):
    fiber_num: int
    total_ports: int = 32
    used_ports: int
    clients: int
    available_ports: int
    load_pct: float


class MuffleCapacityRead(BaseModel):
    muffle_id: UUID
    warning: Optional[str]
    fibers: List[MuffleCapacityFiberRead]


class InfrastructurePortRead(BaseModel):
    panel_id: UUID
    port_id: UUID
    port_number: int
    status: str


class InfrastructurePanelRead(BaseModel):
    panel_id: UUID
    entrance_num: int
    floor_num: int
    label: Optional[str]
    ports: List[InfrastructurePortRead]


class InfrastructureBuildingRead(BaseModel):
    building_id: UUID
    address: str
    city: Optional[str]
    servicing_org_name: Optional[str] = None
    servicing_org_phone: Optional[str] = None
    infrastructure_status: str
    connected_lines: int = 0
    reserved_lines: int = 0
    unclaimed_lines: int = 0
    panels: List[InfrastructurePanelRead]
    notes: List[BuildingNoteRead] = Field(default_factory=list)
    comments: List["OpsCommentRead"] = Field(default_factory=list)


class BuildingSummaryRead(BaseModel):
    building_id: UUID
    address: str
    city: Optional[str]
    servicing_org_name: Optional[str] = None
    servicing_org_phone: Optional[str] = None
    infrastructure_status: str
    metrics: BuildingMetrics
    connected_lines: int = 0
    reserved_lines: int = 0
    unclaimed_lines: int = 0
    notes: List[BuildingNoteRead] = Field(default_factory=list)
    comments: List["OpsCommentRead"] = Field(default_factory=list)


class NetworkPlanCreate(BaseModel):
    tender_id: Optional[UUID] = None
    address: str
    city: Optional[str] = None
    servicing_org_name: Optional[str] = None
    servicing_org_phone: Optional[str] = None
    entrances_count: int = Field(ge=1, le=40)
    floors_count: int = Field(ge=1, le=80)
    flats_per_floor: int = Field(ge=1, le=40)
    floor_height_m: float = Field(default=2.8, ge=2.0, le=6.0)
    panel_every_n_floors: int = Field(default=5, ge=1, le=20)
    distance_from_muffle_m: float = Field(default=0.0, ge=0.0, le=10000.0)
    cable_reserve_pct: int = Field(default=15, ge=0, le=60)
    muffle_id: Optional[UUID] = None
    selected_fibers: List[int] = Field(default_factory=list)


class NetworkPlanRead(BaseModel):
    building_id: UUID
    task_ids: List[UUID]
    warehouse_request_id: Optional[UUID]
    reserved_fibers: List[int]


class DispatchFilterOption(BaseModel):
    value: str
    label: str


class DispatchStatsTaskTypeBreakdown(BaseModel):
    type: TaskType
    total: int
    pending: int
    assigned: int
    in_progress: int
    on_hold: int
    completed: int


class DispatchStatsRead(BaseModel):
    total_tasks: int
    pending_tasks: int
    assigned_tasks: int
    in_progress_tasks: int
    on_hold_tasks: int
    completed_tasks: int
    critical_tasks: int
    unassigned_tasks: int
    avg_estimated_hours: float
    total_estimated_hours: float
    type_breakdown: List[DispatchStatsTaskTypeBreakdown]
    brigade_options: List[DispatchFilterOption]
    city_options: List[DispatchFilterOption]


class WorkerStatsRead(BaseModel):
    user_id: UUID
    name: str
    phone: str
    role: UserRole
    brigade_id: Optional[UUID]
    brigade_name: Optional[str]
    assigned_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    on_hold_events: int
    completed_steps: int
    photo_reports: int
    worklog_entries: int
    total_logged_quantity: float


class SubscriberRequestStatus(str, Enum):
    new = 'new'
    scheduled = 'scheduled'
    in_progress = 'in_progress'
    completed = 'completed'
    postponed = 'postponed'
    canceled = 'canceled'
    no_access = 'no_access'
    technical_issue = 'technical_issue'


class ArrivalWindow(str, Enum):
    before_lunch = 'before_lunch'
    after_lunch = 'after_lunch'


class SubscriberRequestCreate(BaseModel):
    building_id: UUID
    flat_number: int = Field(ge=1)
    customer_name: str = Field(min_length=2)
    phone: str = Field(min_length=5)
    notes: Optional[str] = None


class SubscriberRequestSchedule(BaseModel):
    scheduled_date: date
    arrival_window: ArrivalWindow
    assigned_user_id: UUID


class SubscriberRequestPostpone(BaseModel):
    reason: str = Field(min_length=3)


class OpsContactCreate(BaseModel):
    title: str = Field(min_length=2)
    full_name: Optional[str] = None
    phone: str = Field(min_length=5)
    notes: Optional[str] = None


class OpsContactRead(BaseModel):
    id: UUID
    title: str
    full_name: Optional[str]
    phone: str
    notes: Optional[str]
    created_at: datetime


class SubscriberRequestRead(BaseModel):
    id: UUID
    building_id: UUID
    building_address: str
    city: Optional[str]
    flat_number: int
    customer_name: str
    phone: str
    notes: Optional[str]
    status: SubscriberRequestStatus
    registered_at: datetime
    deadline_at: datetime
    scheduled_date: Optional[date]
    arrival_window: Optional[ArrivalWindow]
    assigned_user_id: Optional[UUID]
    assigned_user_name: Optional[str]
    is_postponed: bool = False
    postponed_reason: Optional[str] = None
    postponed_at: Optional[datetime] = None
    postponed_over_shift: bool = False
    connected_lines: int = 0
    reserved_lines: int = 0
    unclaimed_lines: int = 0
    technical_possible: bool = False
    contacts: List[OpsContactRead] = Field(default_factory=list)
    comments: List[OpsCommentRead] = Field(default_factory=list)


class SubscriberDispatcherSummary(BaseModel):
    total_requests: int
    new_requests: int
    scheduled_requests: int
    overdue_requests: int
    technical_blocked: int
