from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.mission import MissionCreate, MissionUpdate, MissionResponse
from src.services.mission_service import MissionService

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])


def get_service(db: AsyncSession = Depends(get_db)) -> MissionService:
    return MissionService(db)


@router.post("", response_model=MissionResponse, status_code=201)
async def create_mission(
    data: MissionCreate,
    service: MissionService = Depends(get_service),
):
    return await service.create_mission(data)


@router.get("", response_model=list[MissionResponse])
async def list_missions(
    status: Optional[str] = Query(None),
    facility: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    service: MissionService = Depends(get_service),
):
    return await service.list_missions(status=status, facility=facility, limit=limit, offset=offset)


@router.get("/{mission_id}", response_model=MissionResponse)
async def get_mission(
    mission_id: UUID,
    service: MissionService = Depends(get_service),
):
    mission = await service.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.patch("/{mission_id}", response_model=MissionResponse)
async def update_mission(
    mission_id: UUID,
    data: MissionUpdate,
    service: MissionService = Depends(get_service),
):
    mission = await service.update_mission(mission_id, data)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.post("/{mission_id}/assign", response_model=MissionResponse)
async def assign_robot(
    mission_id: UUID,
    service: MissionService = Depends(get_service),
):
    """Auto-allocate the best available robot to this mission."""
    mission = await service.assign_robot(mission_id)
    if not mission:
        raise HTTPException(
            status_code=422,
            detail="No eligible robots available or mission is not in pending state",
        )
    return mission
