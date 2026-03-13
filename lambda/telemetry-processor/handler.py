"""
Lambda: Kinesis → TimescaleDB Telemetry Processor

Triggered by Kinesis Data Stream (telemetry records from robots).
Batch-inserts records into TimescaleDB hypertable.
Failed records are automatically forwarded to SQS DLQ by the event source mapping.
"""
import base64
from datetime import datetime, timezone
import json
import logging
import os

import boto3
import psycopg2
import psycopg2.extras

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DATABASE_URL is fetched from Secrets Manager on first invocation and cached
# for the lifetime of the Lambda container (warm invocations reuse it).
# Fallback to plain env var so local tests / docker-compose still work.
_database_url: str | None = os.environ.get("DATABASE_URL")


def _get_database_url() -> str:
    global _database_url
    if _database_url is None:
        secret_arn = os.environ["DB_SECRET_ARN"]
        client = boto3.client("secretsmanager")
        _database_url = client.get_secret_value(SecretId=secret_arn)["SecretString"]
    return _database_url


def get_connection():
    return psycopg2.connect(_get_database_url())


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
        "sensor_health":     json.dumps(sh) if (sh := payload.get("sensor_health")) else None,
        "mission_id":        payload.get("mission_id"),
        "mission_progress":  payload.get("mission_progress"),
        "speed":             payload.get("speed"),
    }


def _batch_insert(rows: list[dict]) -> None:
    telemetry_sql = """
        INSERT INTO telemetry (
            time, robot_id, battery_level,
            position_x, position_y, position_floor,
            nav_status, motor_load_left, motor_load_right,
            sensor_health, mission_id, mission_progress, speed
        ) VALUES %s
        ON CONFLICT DO NOTHING
    """
    telemetry_values = [
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
            # Insert telemetry history
            psycopg2.extras.execute_values(cur, telemetry_sql, telemetry_values)

            # Upsert robots table: auto-register + update position/status/battery
            for r in rows:
                cur.execute("""
                    INSERT INTO robots (robot_id, name, facility, status, battery_level, position, last_seen)
                    VALUES (%(robot_id)s, %(robot_id)s, 'office_building_a', %(status)s,
                            %(battery)s,
                            jsonb_build_object('x', %(px)s, 'y', %(py)s, 'floor', %(floor)s),
                            NOW())
                    ON CONFLICT (robot_id) DO UPDATE SET
                        status       = EXCLUDED.status,
                        battery_level = EXCLUDED.battery_level,
                        position     = EXCLUDED.position,
                        last_seen    = NOW(),
                        updated_at   = NOW()
                """, {
                    "robot_id": r["robot_id"],
                    "status":   r["nav_status"] or "idle",
                    "battery":  r["battery_level"],
                    "px":       r["position_x"],
                    "py":       r["position_y"],
                    "floor":    r["position_floor"] or 1,
                })
        conn.commit()
    finally:
        conn.close()
