import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import MissionORM
from src.models.mission import MissionCreate, MissionUpdate, MissionResponse, MissionStatus, RobotCandidate
from src.services.allocator import allocate

logger = logging.getLogger(__name__)
FLEET_SERVICE_URL = os.getenv("FLEET_SERVICE_URL", "http://fleet-service:8000")


class MissionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_mission(self, data: MissionCreate) -> MissionResponse:
        mission = MissionORM(
            name=data.name,
            facility=data.facility,
            zone=data.zone,
            priority=data.priority,
            scheduled_at=data.scheduled_at,
            created_by=data.created_by,
        )
        self.db.add(mission)
        await self.db.commit()
        await self.db.refresh(mission)
        return self._to_response(mission)

    async def get_mission(self, mission_id: UUID) -> Optional[MissionResponse]:
        result = await self.db.execute(
            select(MissionORM).where(MissionORM.id == mission_id)
        )
        mission = result.scalar_one_or_none()
        return self._to_response(mission) if mission else None

    async def list_missions(
        self,
        status: Optional[str] = None,
        facility: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MissionResponse]:
        query = select(MissionORM)
        if status:
            query = query.where(MissionORM.status == status)
        if facility:
            query = query.where(MissionORM.facility == facility)
        query = query.order_by(MissionORM.priority, MissionORM.scheduled_at).limit(limit).offset(offset)

        result = await self.db.execute(query)
        return [self._to_response(m) for m in result.scalars().all()]

    async def update_mission(self, mission_id: UUID, data: MissionUpdate) -> Optional[MissionResponse]:
        result = await self.db.execute(
            select(MissionORM).where(MissionORM.id == mission_id)
        )
        mission = result.scalar_one_or_none()
        if not mission:
            return None

        if data.status:
            mission.status = data.status.value
            if data.status == MissionStatus.IN_PROGRESS and not mission.started_at:
                mission.started_at = datetime.now(timezone.utc)
            elif data.status in (MissionStatus.COMPLETED, MissionStatus.FAILED):
                mission.completed_at = datetime.now(timezone.utc)

        if data.assigned_robot is not None:
            mission.assigned_robot = data.assigned_robot
        if data.coverage_pct is not None:
            mission.coverage_pct = data.coverage_pct

        mission.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(mission)
        return self._to_response(mission)

    async def assign_robot(self, mission_id: UUID) -> Optional[MissionResponse]:
        """Auto-allocate the best available robot to a mission."""
        result = await self.db.execute(
            select(MissionORM).where(MissionORM.id == mission_id)
        )
        mission = result.scalar_one_or_none()
        if not mission or mission.status != MissionStatus.PENDING.value:
            return None

        # Fetch idle robots from fleet service
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{FLEET_SERVICE_URL}/api/v1/robots",
                    params={"status": "idle"},
                )
                resp.raise_for_status()
                robots_data = resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch robots from fleet service: {e}")
            return None

        candidates = [
            RobotCandidate(
                robot_id=r["robot_id"],
                battery_level=r.get("battery_level", 0),
                position_x=r.get("position", {}).get("x", 0) if r.get("position") else 0,
                position_y=r.get("position", {}).get("y", 0) if r.get("position") else 0,
                status=r["status"],
            )
            for r in robots_data
        ]

        # Zone centroid is zone name-based for now; extend with zone DB lookup later
        robot_id = allocate(candidates, zone_x=0.0, zone_y=0.0)
        if not robot_id:
            return None

        mission.assigned_robot = None  # will store UUID when fleet returns UUID
        mission.status = MissionStatus.ASSIGNED.value
        mission.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(mission)
        return self._to_response(mission)

    @staticmethod
    def _to_response(mission: MissionORM) -> MissionResponse:
        return MissionResponse(
            id=mission.id,
            name=mission.name,
            facility=mission.facility,
            zone=mission.zone,
            priority=mission.priority,
            status=MissionStatus(mission.status),
            assigned_robot=mission.assigned_robot,
            scheduled_at=mission.scheduled_at,
            started_at=mission.started_at,
            completed_at=mission.completed_at,
            coverage_pct=mission.coverage_pct or 0.0,
            created_by=mission.created_by,
            created_at=mission.created_at,
            updated_at=mission.updated_at,
        )
