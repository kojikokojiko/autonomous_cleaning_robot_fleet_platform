from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class TelemetryPoint(BaseModel):
    time: datetime
    robot_id: str
    battery_level: Optional[float] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    position_floor: Optional[int] = None
    nav_status: Optional[str] = None
    motor_load_left: Optional[float] = None
    motor_load_right: Optional[float] = None
    mission_progress: Optional[float] = None
    speed: Optional[float] = None
