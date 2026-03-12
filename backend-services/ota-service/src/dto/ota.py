from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class FirmwareCreate(BaseModel):
    version: str
    checksum_sha256: Optional[str] = None  # auto-computed; ignored if provided
    file_size_bytes: Optional[int] = None  # auto-computed; ignored if provided
    release_notes: Optional[str] = None
    is_stable: bool = False
    config: Optional[dict] = None
    uploaded_by: Optional[str] = None


class FirmwareResponse(BaseModel):
    id: UUID
    version: str
    s3_key: str
    checksum_sha256: str
    file_size_bytes: Optional[int] = None
    release_notes: Optional[str] = None
    is_stable: bool
    config: Optional[dict] = None
    uploaded_by: Optional[str] = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class OTAJobCreate(BaseModel):
    firmware_id: UUID
    robot_ids: list[str]
    strategy: Literal["rolling", "canary"] = "rolling"


class OTAJobStatusUpdate(BaseModel):
    status: str
    error_message: Optional[str] = None


class OTAJobResponse(BaseModel):
    id: UUID
    firmware_id: UUID
    robot_id: UUID
    strategy: str
    status: str
    attempts: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
