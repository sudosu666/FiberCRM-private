from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    Designer = 'Designer'
    Dispatcher = 'Dispatcher'
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
    completed = 'completed'
    canceled = 'canceled'


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class TokenData(BaseModel):
    phone: Optional[str] = None
    role: Optional[UserRole] = None


class UserCreate(BaseModel):
    name: str
    phone: str
    password: str
    email: Optional[str] = None
    role: UserRole = UserRole.Dispatcher


class UserRead(BaseModel):
    id: UUID
    name: str
    phone: str
    email: Optional[str]
    role: UserRole
    is_active: bool

    class Config:
        orm_mode = True


class TaskBase(BaseModel):
    type: TaskType
    building_id: Optional[UUID]
    brigade_id: Optional[UUID]
    priority: int = Field(0, ge=0)


class TaskRead(TaskBase):
    id: UUID
    status: TaskStatus
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        orm_mode = True


class TenderRead(BaseModel):
    id: UUID
    name: str
    status: TenderStatus
    customer: str
    created_at: datetime

    class Config:
        orm_mode = True


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
    building_address: Optional[str]
    brigade_name: Optional[str]
    estimated_hours: Optional[float]
    metrics: BuildingMetrics


class TaskAssignRequest(BaseModel):
    brigade_id: UUID


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


class WarehouseRequestItemRead(BaseModel):
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


class NetworkFiberRead(BaseModel):
    id: UUID
    fiber_number: int
    status: str


class NetworkMuffleRead(BaseModel):
    id: UUID
    name: Optional[str]
    address_note: Optional[str]
    capacity: int
    fibers: List[NetworkFiberRead]


class BuildingNetworkRead(BaseModel):
    id: UUID
    address: str
    metrics: BuildingMetrics
