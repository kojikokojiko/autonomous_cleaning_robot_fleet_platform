"""
Lambda: Kinesis → TimescaleDB Telemetry Processor

Triggered by Kinesis Data Stream (telemetry records from robots).
Batch-inserts records into TimescaleDB hypertable.
Failed records are automatically forwarded to SQS DLQ by the event source mapping.
"""
import base64
import json
import logging
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def lambda_handler(event, context):
    records = event.get("Records", [])
    logger.info(f"Processing {len(records)} Kinesis records")

    rows = []
    for record in records:
        try:
            payload = json.loads(
                base64.b64decode(record["kinesis"]["data"]).decode("utf-8")
            )
            row = _parse_telemetry(payload)
            if row:
                rows.append(row)
        except Exception as e:
            logger.error(f"Failed to parse record: {e}", exc_info=True)
            raise  # Let Lambda retry / send to DLQ

    if not rows:
        return {"statusCode": 200, "inserted": 0}

    _batch_insert(rows)
    logger.info(f"Inserted {len(rows)} telemetry records")
    return {"statusCode": 200, "inserted": len(rows)}


def _parse_telemetry(payload: dict) -> dict | None:
    robot_id = payload.get("robot_id")
    if not robot_id:
        logger.warning(f"Missing robot_id in payload: {payload}")
        return None

    timestamp_str = payload.get("timestamp")
    try:
        ts = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now(timezone.utc)
    except ValueError:
        ts = datetime.now(timezone.utc)

    position = payload.get("position", {})
    return {
        "time":              ts,
        "robot_id":          robot_id,
        "battery_level":     payload.get("battery_level"),
        "position_x":        position.get("x"),
        "position_y":        position.get("y"),
        "position_floor":    position.get("floor", 1),
        "nav_status":        payload.get("nav_status"),
        "motor_load_left":   payload.get("motor_load_left"),
        "motor_load_right":  payload.get("motor_load_right"),
        "sensor_health":     json.dumps(payload.get("sensor_health")) if payload.get("sensor_health") else None,
        "mission_id":        payload.get("mission_id"),
        "mission_progress":  payload.get("mission_progress"),
        "speed":             payload.get("speed"),
    }


def _batch_insert(rows: list[dict]) -> None:
    insert_sql = """
        INSERT INTO telemetry (
            time, robot_id, battery_level,
            position_x, position_y, position_floor,
            nav_status, motor_load_left, motor_load_right,
            sensor_health, mission_id, mission_progress, speed
        ) VALUES %s
        ON CONFLICT DO NOTHING
    """
    values = [
        (
            r["time"], r["robot_id"], r["battery_level"],
            r["position_x"], r["position_y"], r["position_floor"],
            r["nav_status"], r["motor_load_left"], r["motor_load_right"],
            r["sensor_health"], r["mission_id"], r["mission_progress"], r["speed"],
        )
        for r in rows
    ]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, insert_sql, values)
        conn.commit()
    finally:
        conn.close()
