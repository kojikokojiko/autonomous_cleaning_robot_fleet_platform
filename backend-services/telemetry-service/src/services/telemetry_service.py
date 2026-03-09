import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.telemetry import TelemetryPoint

logger = logging.getLogger(__name__)


class TelemetryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_telemetry(
        self,
        robot_id: str,
        from_ts: Optional[datetime],
        to_ts: Optional[datetime],
        limit: int,
    ) -> list[TelemetryPoint]:
        if from_ts is None:
            from_ts = datetime.utcfromtimestamp(0)
        if to_ts is None:
            to_ts = datetime.utcnow()

        result = await self.db.execute(
            text(
                "SELECT * FROM telemetry "
                "WHERE robot_id = :robot_id "
                "AND time BETWEEN :from_ts AND :to_ts "
                "ORDER BY time DESC "
                "LIMIT :limit"
            ),
            {"robot_id": robot_id, "from_ts": from_ts, "to_ts": to_ts, "limit": limit},
        )
        rows = result.mappings().all()
        return [TelemetryPoint(**dict(row)) for row in rows]

    async def get_latest(self, robot_id: str) -> Optional[TelemetryPoint]:
        result = await self.db.execute(
            text(
                "SELECT * FROM telemetry "
                "WHERE robot_id = :robot_id "
                "ORDER BY time DESC "
                "LIMIT 1"
            ),
            {"robot_id": robot_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return TelemetryPoint(**dict(row))
