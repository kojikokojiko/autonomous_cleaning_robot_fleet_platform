import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import RobotORM
from src.models.robot import RobotCreate, RobotUpdate, RobotResponse, FleetSummary, RobotStatus, Position

logger = logging.getLogger(__name__)


class FleetService:
    def __init__(self, db: AsyncSession, redis=None):
        self.db = db
        self.redis = redis

    async def register_robot(self, data: RobotCreate) -> RobotResponse:
        robot = RobotORM(
            robot_id=data.robot_id,
            name=data.name,
            facility=data.facility,
            model=data.model,
        )
        self.db.add(robot)
        await self.db.commit()
        await self.db.refresh(robot)
        return self._to_response(robot)

    async def get_robot(self, robot_id: str) -> Optional[RobotResponse]:
        result = await self.db.execute(
            select(RobotORM).where(RobotORM.robot_id == robot_id)
        )
        robot = result.scalar_one_or_none()
        if not robot:
            return None
        return self._to_response(robot)

    async def list_robots(
        self,
        facility: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RobotResponse]:
        query = select(RobotORM)
        if facility:
            query = query.where(RobotORM.facility == facility)
        if status:
            query = query.where(RobotORM.status == status)
        query = query.limit(limit).offset(offset).order_by(RobotORM.registered_at.desc())

        result = await self.db.execute(query)
        robots = result.scalars().all()
        return [self._to_response(r) for r in robots]

    async def update_robot(self, robot_id: str, data: RobotUpdate) -> Optional[RobotResponse]:
        result = await self.db.execute(
            select(RobotORM).where(RobotORM.robot_id == robot_id)
        )
        robot = result.scalar_one_or_none()
        if not robot:
            return None

        update_data = data.model_dump(exclude_none=True)
        if "position" in update_data:
            pos = update_data.pop("position")
            robot.position_x = pos["x"]
            robot.position_y = pos["y"]
            robot.position_floor = pos.get("floor", 1)

        for key, value in update_data.items():
            setattr(robot, key, value)

        robot.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(robot)

        # Update digital twin cache
        if self.redis:
            await self._update_twin_cache(robot)

        return self._to_response(robot)

    async def update_telemetry(
        self,
        robot_id: str,
        battery_level: float,
        position: dict,
        status: str,
    ) -> None:
        """Fast path: update robot's live state from telemetry."""
        await self.db.execute(
            update(RobotORM)
            .where(RobotORM.robot_id == robot_id)
            .values(
                battery_level=battery_level,
                position_x=position.get("x"),
                position_y=position.get("y"),
                position_floor=position.get("floor", 1),
                status=status,
                last_seen=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.db.commit()

    async def get_fleet_summary(self, facility: Optional[str] = None) -> FleetSummary:
        query = select(RobotORM)
        if facility:
            query = query.where(RobotORM.facility == facility)
        result = await self.db.execute(query)
        robots = result.scalars().all()

        total = len(robots)
        status_counts = {s: 0 for s in RobotStatus}
        batteries = []
        for r in robots:
            try:
                status_counts[RobotStatus(r.status)] += 1
            except ValueError:
                pass
            if r.battery_level is not None:
                batteries.append(r.battery_level)

        online = total - status_counts[RobotStatus.OFFLINE]
        return FleetSummary(
            total=total,
            online=online,
            cleaning=status_counts[RobotStatus.CLEANING],
            idle=status_counts[RobotStatus.IDLE],
            charging=status_counts[RobotStatus.CHARGING] + status_counts[RobotStatus.DOCKED],
            error=status_counts[RobotStatus.ERROR],
            avg_battery=sum(batteries) / len(batteries) if batteries else None,
        )

    async def _update_twin_cache(self, robot: RobotORM) -> None:
        twin = {
            "robot_id": robot.robot_id,
            "name": robot.name,
            "status": robot.status,
            "battery": robot.battery_level,
            "position": {
                "x": robot.position_x,
                "y": robot.position_y,
                "floor": robot.position_floor,
            },
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        await self.redis.setex(
            f"twin:{robot.robot_id}",
            300,  # 5 min TTL
            json.dumps(twin),
        )

    @staticmethod
    def _to_response(robot: RobotORM) -> RobotResponse:
        position = None
        if robot.position_x is not None and robot.position_y is not None:
            position = Position(
                x=robot.position_x,
                y=robot.position_y,
                floor=robot.position_floor or 1,
            )
        return RobotResponse(
            id=robot.id,
            robot_id=robot.robot_id,
            name=robot.name,
            facility=robot.facility,
            model=robot.model,
            firmware_version=robot.firmware_version,
            status=RobotStatus(robot.status),
            battery_level=robot.battery_level,
            position=position,
            last_seen=robot.last_seen,
            registered_at=robot.registered_at,
            updated_at=robot.updated_at,
        )
