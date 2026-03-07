from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

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

class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[UserRole] = None

class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.dispatcher

class UserRead(BaseModel):
    id: str
    username: str
    role: UserRole
    is_active: bool
    class Config:
        orm_mode = True

class TaskBase(BaseModel):
    type: TaskType
    building_id: Optional[str]
    brigade_id: Optional[str]
    priority: int = Field(0, ge=0)

class TaskRead(TaskBase):
    id: str
    status: TaskStatus
    created_at: datetime
    completed_at: Optional[datetime]
    class Config:
        orm_mode = True

class TenderRead(BaseModel):
    id: str
    name: str
    status: TenderStatus
    customer: str
    created_at: datetime
    class Config:
        orm_mode = True
