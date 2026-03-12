"""
Redis pub/sub subscriber: forwards ws:updates channel to WebSocket clients.
"""
import asyncio
import json
import logging
import os

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


async def subscribe_and_forward(manager) -> None:
    """Subscribe to Redis 'ws:updates' and broadcast to WebSocket clients."""
    while True:
        try:
            redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            pubsub = redis.pubsub()
            await pubsub.subscribe("ws:updates")
            logger.info("Redis subscriber listening on ws:updates")
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await manager.broadcast(data)
                except Exception as exc:
                    logger.warning("Failed to broadcast WS message: %s", exc)
        except Exception as exc:
            logger.error("Redis subscriber error: %s — retrying in 3s", exc)
            await asyncio.sleep(3)
