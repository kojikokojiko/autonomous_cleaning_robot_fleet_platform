from enum import Enum
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class RobotStatus(str, Enum):
    OFFLINE    = "offline"
    IDLE       = "idle"
    CLEANING   = "cleaning"
    CHARGING   = "charging"
    DOCKED     = "docked"
    ERROR      = "error"
    OTA_UPDATE = "ota_update"


class Position(BaseModel):
    x: float
    y: float
    floor: int = 1


class RobotCreate(BaseModel):
    robot_id: str = Field(..., max_length=64)
    name: str = Field(..., max_length=128)
    facility: Optional[str] = None
    model: Optional[str] = None


class RobotUpdate(BaseModel):
    name: Optional[str] = None
    facility: Optional[str] = None
    status: Optional[RobotStatus] = None
    battery_level: Optional[float] = Field(None, ge=0, le=100)
    position: Optional[Position] = None
    firmware_version: Optional[str] = None


class RobotResponse(BaseModel):
    id: UUID
    robot_id: str
    name: str
    facility: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    status: RobotStatus
    battery_level: Optional[float] = None
    position: Optional[Position] = None
    last_seen: Optional[datetime] = None
    registered_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FleetSummary(BaseModel):
    total: int
    online: int
    cleaning: int
    idle: int
    charging: int
    error: int
    avg_battery: Optional[float] = None
