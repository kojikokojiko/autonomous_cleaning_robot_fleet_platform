from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.command import CommandCreate, CommandResponse
from src.services.command_service import CommandService
from src.services.websocket_manager import manager

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])
ws_router = APIRouter(tags=["websocket"])


def get_service(db: AsyncSession = Depends(get_db)) -> CommandService:
    return CommandService(db)


@router.post("", response_model=CommandResponse, status_code=201)
async def issue_command(
    data: CommandCreate,
    service: CommandService = Depends(get_service),
):
    try:
        return await service.issue_command(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{command_id}", response_model=CommandResponse)
async def get_command(
    command_id: UUID,
    service: CommandService = Depends(get_service),
):
    cmd = await service.get_command(command_id)
    if cmd is None:
        raise HTTPException(status_code=404, detail=f"Command '{command_id}' not found")
    return cmd


@router.get("", response_model=list[CommandResponse])
async def list_commands(
    robot_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    service: CommandService = Depends(get_service),
):
    return await service.list_commands(robot_id=robot_id, status=status, limit=limit)


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
