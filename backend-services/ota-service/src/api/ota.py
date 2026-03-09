from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.ota import (
    FirmwareCreate,
    FirmwareResponse,
    OTAJobCreate,
    OTAJobResponse,
    OTAJobStatusUpdate,
)
from src.services.ota_service import OTAService

router = APIRouter(prefix="/api/v1/ota", tags=["ota"])


def get_service(db: AsyncSession = Depends(get_db)) -> OTAService:
    return OTAService(db)


@router.post("/firmware", response_model=FirmwareResponse, status_code=201)
async def create_firmware(
    data: FirmwareCreate,
    service: OTAService = Depends(get_service),
):
    return await service.create_firmware(data)


@router.get("/firmware", response_model=list[FirmwareResponse])
async def list_firmware(
    service: OTAService = Depends(get_service),
):
    return await service.list_firmware()


@router.post("/jobs", response_model=list[OTAJobResponse], status_code=201)
async def create_jobs(
    data: OTAJobCreate,
    service: OTAService = Depends(get_service),
):
    try:
        return await service.create_jobs(data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/jobs", response_model=list[OTAJobResponse])
async def list_jobs(
    robot_id: Optional[str] = Query(None),
    service: OTAService = Depends(get_service),
):
    return await service.list_jobs(robot_id=robot_id)


@router.patch("/jobs/{job_id}", response_model=OTAJobResponse)
async def update_job_status(
    job_id: UUID,
    data: OTAJobStatusUpdate,
    service: OTAService = Depends(get_service),
):
    job = await service.update_job_status(job_id, data.status)
    if job is None:
        raise HTTPException(status_code=404, detail=f"OTA job '{job_id}' not found")
    return job
