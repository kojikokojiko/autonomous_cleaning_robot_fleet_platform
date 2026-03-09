from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.robot import RobotCreate, RobotUpdate, RobotResponse, FleetSummary
from src.services.fleet_service import FleetService

router = APIRouter(prefix="/api/v1/robots", tags=["robots"])


def get_service(db: AsyncSession = Depends(get_db)) -> FleetService:
    return FleetService(db)


@router.post("", response_model=RobotResponse, status_code=201)
async def register_robot(
    data: RobotCreate,
    service: FleetService = Depends(get_service),
):
    return await service.register_robot(data)


@router.get("", response_model=list[RobotResponse])
async def list_robots(
    facility: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    service: FleetService = Depends(get_service),
):
    return await service.list_robots(facility=facility, status=status, limit=limit, offset=offset)


@router.get("/summary", response_model=FleetSummary)
async def fleet_summary(
    facility: Optional[str] = Query(None),
    service: FleetService = Depends(get_service),
):
    return await service.get_fleet_summary(facility=facility)


@router.get("/{robot_id}", response_model=RobotResponse)
async def get_robot(
    robot_id: str,
    service: FleetService = Depends(get_service),
):
    robot = await service.get_robot(robot_id)
    if not robot:
        raise HTTPException(status_code=404, detail=f"Robot '{robot_id}' not found")
    return robot


@router.patch("/{robot_id}", response_model=RobotResponse)
async def update_robot(
    robot_id: str,
    data: RobotUpdate,
    service: FleetService = Depends(get_service),
):
    robot = await service.update_robot(robot_id, data)
    if not robot:
        raise HTTPException(status_code=404, detail=f"Robot '{robot_id}' not found")
    return robot
