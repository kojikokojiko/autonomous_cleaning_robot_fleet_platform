from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.twin import TwinState, TwinSnapshot
from src.services.twin_service import TwinService, get_redis_client

router = APIRouter(prefix="/api/v1/twins", tags=["twins"])


async def get_service(db: AsyncSession = Depends(get_db)) -> TwinService:
    redis = get_redis_client()
    return TwinService(db, redis)


@router.get("/{robot_id}", response_model=TwinState)
async def get_twin(
    robot_id: str,
    service: TwinService = Depends(get_service),
):
    twin = await service.get_twin(robot_id)
    if twin is None:
        raise HTTPException(status_code=404, detail=f"No twin state found for robot '{robot_id}'")
    return twin


@router.get("/{robot_id}/history", response_model=list[TwinSnapshot])
async def get_twin_history(
    robot_id: str,
    limit: int = Query(20, ge=1, le=200),
    service: TwinService = Depends(get_service),
):
    return await service.get_history(robot_id, limit)


@router.put("/{robot_id}", response_model=TwinState)
async def update_twin(
    robot_id: str,
    state: TwinState,
    service: TwinService = Depends(get_service),
):
    return await service.update_twin(robot_id, state)
