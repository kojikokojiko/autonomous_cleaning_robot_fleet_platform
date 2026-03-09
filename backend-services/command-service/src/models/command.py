from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class CommandCreate(BaseModel):
    robot_id: str
    command_type: str
    payload: Optional[dict] = None
    issued_by: Optional[str] = None


class CommandResponse(BaseModel):
    id: UUID
    robot_id: str
    command_type: str
    payload: Optional[dict] = None
    status: str
    issued_by: Optional[str] = None
    issued_at: datetime
    acknowledged_at: Optional[datetime] = None
    retry_count: int

    model_config = {"from_attributes": True}
