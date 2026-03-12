from datetime import datetime, timezone
import json
import logging
import os
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TwinSnapshotORM
from src.dto.twin import TwinSnapshot, TwinState

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TWIN_TTL = 300


def get_redis_client():
    return aioredis.from_url(REDIS_URL, decode_responses=True)


class TwinService:
    def __init__(self, db: AsyncSession, redis):
        self.db = db
        self.redis = redis

    async def get_twin(self, robot_id: str) -> Optional[TwinState]:
        key = f"twin:{robot_id}"
        cached = await self.redis.get(key)
        if cached:
            data = json.loads(cached)
            return TwinState(**data)

        result = await self.db.execute(
            select(TwinSnapshotORM)
            .where(TwinSnapshotORM.robot_id == robot_id)
            .order_by(TwinSnapshotORM.snapshotted_at.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            return None

        state = TwinState(**snapshot.state)
        await self.redis.setex(key, TWIN_TTL, json.dumps(snapshot.state, default=str))
        return state

    async def get_history(self, robot_id: str, limit: int) -> list[TwinSnapshot]:
        result = await self.db.execute(
            select(TwinSnapshotORM)
            .where(TwinSnapshotORM.robot_id == robot_id)
            .order_by(TwinSnapshotORM.snapshotted_at.desc())
            .limit(limit)
        )
        snapshots = result.scalars().all()
        return [TwinSnapshot.model_validate(s) for s in snapshots]

    async def update_twin(self, robot_id: str, state: TwinState) -> TwinState:
        state.robot_id = robot_id
        state.last_updated = datetime.now(timezone.utc)

        state_dict = state.model_dump(mode="json")

        key = f"twin:{robot_id}"
        await self.redis.setex(key, TWIN_TTL, json.dumps(state_dict, default=str))

        snapshot = TwinSnapshotORM(robot_id=robot_id, state=state_dict)
        self.db.add(snapshot)
        await self.db.commit()

        return state
