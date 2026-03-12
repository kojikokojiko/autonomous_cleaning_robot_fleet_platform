from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class MissionStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MissionCreate(BaseModel):
    name: str
    facility: str
    zone: str
    priority: int = 5
    scheduled_at: datetime
    created_by: Optional[str] = None


class Mission(BaseModel):
    id: UUID
    name: str
    facility: Optional[str] = None
    zone: str
    priority: int
    status: MissionStatus
    assigned_robot: Optional[UUID] = None
    scheduled_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    coverage_pct: float = 0.0
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
