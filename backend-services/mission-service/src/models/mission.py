from enum import Enum
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class MissionStatus(str, Enum):
    PENDING     = "pending"
    ASSIGNED    = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"
    CANCELLED   = "cancelled"


class MissionCreate(BaseModel):
    name: str = Field(..., max_length=128)
    facility: str
    zone: str = Field(..., max_length=64)
    priority: int = Field(5, ge=1, le=10)
    scheduled_at: datetime
    created_by: Optional[str] = None


class MissionUpdate(BaseModel):
    status: Optional[MissionStatus] = None
    assigned_robot: Optional[UUID] = None
    coverage_pct: Optional[float] = Field(None, ge=0, le=100)


class MissionResponse(BaseModel):
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

    model_config = {"from_attributes": True}


class RobotCandidate(BaseModel):
    """Robot candidate for task allocation scoring."""
    robot_id: str
    battery_level: float
    position_x: float
    position_y: float
    status: str
