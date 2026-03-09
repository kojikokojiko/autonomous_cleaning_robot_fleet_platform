"""
Lambda: WebSocket Connection Manager

Handles $connect and $disconnect routes from API Gateway WebSocket API.
Stores active connectionIds in Redis Set keyed by "ws:connections".

$connect  → store connectionId in Redis
$disconnect → remove connectionId from Redis

On $connect, validates the JWT token passed as ?token= query parameter
(full Cognito validation is handled by the API Gateway custom authorizer).
"""
import json
import logging
import os

import redis

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
WS_CONNECTIONS_KEY = "ws:connections"

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    return _redis_client


def lambda_handler(event, context):
    route_key = event.get("requestContext", {}).get("routeKey", "$default")
    connection_id = event.get("requestContext", {}).get("connectionId")

    logger.info(f"WebSocket route={route_key} connectionId={connection_id}")

    if route_key == "$connect":
        return _on_connect(connection_id, event)
    elif route_key == "$disconnect":
        return _on_disconnect(connection_id)
    else:
        return _on_default(connection_id, event)


def _on_connect(connection_id: str, event: dict) -> dict:
    r = _get_redis()
    r.sadd(WS_CONNECTIONS_KEY, connection_id)
    # Optionally store metadata (e.g., user info from authorizer context)
    authorizer_context = event.get("requestContext", {}).get("authorizer", {})
    if authorizer_context:
        r.setex(
            f"ws:conn:{connection_id}",
            3600,  # 1h TTL
            json.dumps(authorizer_context),
        )
    logger.info(f"Connected: {connection_id} (total: {r.scard(WS_CONNECTIONS_KEY)})")
    return {"statusCode": 200}


def _on_disconnect(connection_id: str) -> dict:
    r = _get_redis()
    r.srem(WS_CONNECTIONS_KEY, connection_id)
    r.delete(f"ws:conn:{connection_id}")
    logger.info(f"Disconnected: {connection_id} (remaining: {r.scard(WS_CONNECTIONS_KEY)})")
    return {"statusCode": 200}


def _on_default(connection_id: str, event: dict) -> dict:
    # Echo back for debugging
    logger.info(f"Default route from {connection_id}: {event.get('body', '')}")
    return {"statusCode": 200}
