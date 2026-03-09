from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RobotStatus(str, Enum):
    OFFLINE    = "offline"
    IDLE       = "idle"
    CLEANING   = "cleaning"
    CHARGING   = "charging"
    DOCKED     = "docked"
    ERROR      = "error"
    OTA_UPDATE = "ota_update"


@dataclass
class RobotState:
    robot_id: str
    status: RobotStatus = RobotStatus.IDLE
    battery_level: float = 100.0
    position_x: float = 0.0
    position_y: float = 0.0
    floor: int = 1
    nav_status: str = "idle"
    motor_load_left: float = 0.0
    motor_load_right: float = 0.0
    speed: float = 0.0
    mission_progress: Optional[float] = None
    sensor_health: dict = field(default_factory=lambda: {
        "lidar": "ok",
        "camera": "ok",
        "imu": "ok",
        "bumper": "ok",
    })
