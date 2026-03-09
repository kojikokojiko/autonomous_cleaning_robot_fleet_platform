from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class TwinState(BaseModel):
    robot_id: str
    position: Optional[dict] = None  # {"x": float, "y": float, "floor": int}
    battery: Optional[float] = None
    status: Optional[str] = None
    mission: Optional[str] = None
    last_updated: Optional[datetime] = None


class TwinSnapshot(BaseModel):
    id: UUID
    robot_id: str
    state: dict
    snapshotted_at: datetime

    model_config = {"from_attributes": True}
