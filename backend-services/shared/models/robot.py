from enum import Enum
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class RobotStatus(str, Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    CLEANING = "cleaning"
    CHARGING = "charging"
    DOCKED = "docked"
    ERROR = "error"
    OTA_UPDATE = "ota_update"


class Position(BaseModel):
    x: float
    y: float
    floor: int = 1


class RobotBase(BaseModel):
    robot_id: str
    name: str
    facility: Optional[str] = None
    model: Optional[str] = None


class RobotCreate(RobotBase):
    pass


class Robot(RobotBase):
    id: UUID
    firmware_version: Optional[str] = None
    status: RobotStatus = RobotStatus.OFFLINE
    battery_level: Optional[float] = None
    position: Optional[Position] = None
    last_seen: Optional[datetime] = None
    registered_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RobotTelemetry(BaseModel):
    robot_id: str
    timestamp: datetime
    battery_level: float
    position: Position
    nav_status: str
    motor_load_left: Optional[float] = None
    motor_load_right: Optional[float] = None
    sensor_health: Optional[dict] = None
    mission_id: Optional[str] = None
    mission_progress: Optional[float] = None
    speed: Optional[float] = None
