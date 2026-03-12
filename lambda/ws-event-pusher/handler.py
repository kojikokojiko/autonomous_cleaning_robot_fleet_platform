"""
Lambda: EventBridge → WebSocket Event Pusher

Triggered by EventBridge when robot events arrive.
Retrieves all active WebSocket connectionIds from Redis,
then posts the event to each connection via API Gateway Management API.

Stale connections (gone) are automatically cleaned from Redis.
"""
import json
import logging
import os

import boto3
from botocore.exceptions import ClientError
import redis

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
WS_API_ENDPOINT = os.environ.get("WS_API_ENDPOINT", "")  # e.g. https://xxx.execute-api.ap-northeast-1.amazonaws.com/dev
WS_CONNECTIONS_KEY = "ws:connections"

_redis_client = None
_apigw_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    return _redis_client


def _get_apigw():
    global _apigw_client
    if _apigw_client is None and WS_API_ENDPOINT:
        endpoint_url = WS_API_ENDPOINT.replace("wss://", "https://").replace("ws://", "http://")
        _apigw_client = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=endpoint_url,
        )
    return _apigw_client


def lambda_handler(event, context):
    """
    EventBridge event shape:
    {
      "source": "robotops.robot",
      "detail-type": "RobotBatteryLow",
      "detail": { "robot_id": "...", ... }
    }
    """
    detail_type = event.get("detail-type", "UnknownEvent")
    detail = event.get("detail", {})

    push_payload = json.dumps({
        "type": "robot_event",
        "event_type": detail_type,
        "data": detail,
    }).encode("utf-8")

    _push_to_all_connections(push_payload)
    return {"statusCode": 200}


def _push_to_all_connections(payload: bytes) -> None:
    r = _get_redis()
    connection_ids = r.smembers(WS_CONNECTIONS_KEY)

    if not connection_ids:
        logger.info("No active WebSocket connections")
        return

    apigw = _get_apigw()
    if not apigw:
        logger.warning("API Gateway client not initialized (WS_API_ENDPOINT not set)")
        return

    stale = []
    for conn_id in connection_ids:
        try:
            apigw.post_to_connection(ConnectionId=conn_id, Data=payload)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("GoneException", "ForbiddenException"):
                logger.info(f"Removing stale connection: {conn_id}")
                stale.append(conn_id)
            else:
                logger.error(f"Failed to push to {conn_id}: {e}")

    if stale:
        r.srem(WS_CONNECTIONS_KEY, *stale)

    logger.info(f"Pushed to {len(connection_ids) - len(stale)} connections")
