from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.telemetry import TelemetryPoint
from src.services.telemetry_service import TelemetryService

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


def get_service(db: AsyncSession = Depends(get_db)) -> TelemetryService:
    return TelemetryService(db)


@router.get("/{robot_id}", response_model=list[TelemetryPoint])
async def get_telemetry(
    robot_id: str,
    from_ts: Optional[datetime] = Query(None),
    to_ts: Optional[datetime] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    service: TelemetryService = Depends(get_service),
):
    return await service.get_telemetry(robot_id, from_ts, to_ts, limit)


@router.get("/{robot_id}/latest", response_model=TelemetryPoint)
async def get_latest(
    robot_id: str,
    service: TelemetryService = Depends(get_service),
):
    point = await service.get_latest(robot_id)
    if point is None:
        raise HTTPException(status_code=404, detail=f"No telemetry found for robot '{robot_id}'")
    return point
