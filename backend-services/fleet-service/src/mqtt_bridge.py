"""
MQTT Bridge - subscribes to robot telemetry/events and updates fleet state.

Runs as a background asyncio task inside fleet-service.
Topics:
  robot/+/telemetry  -> update robots table (status, battery, position, last_seen)
  robot/+/events     -> insert into events table
"""
import asyncio
from datetime import datetime, timezone
import json
import logging
import os

import paho.mqtt.client as mqtt
import redis.asyncio as aioredis

from src.db.session import AsyncSessionLocal
from src.services.fleet_service import FleetService

logger = logging.getLogger(__name__)

MQTT_BROKER          = os.getenv("MQTT_BROKER", "mqtt-broker")
MQTT_PORT            = int(os.getenv("MQTT_PORT", "1883"))
REDIS_URL            = os.getenv("REDIS_URL", "redis://redis:6379")
MISSION_SERVICE_URL  = os.getenv("MISSION_SERVICE_URL", "http://mission-service:8000")
OTA_SERVICE_URL      = os.getenv("OTA_SERVICE_URL", "http://ota-service:8000")


class MQTTBridge:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._redis: aioredis.Redis | None = None
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id="fleet-service-bridge",
            clean_session=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"MQTT bridge connected to {MQTT_BROKER}:{MQTT_PORT}")
            client.subscribe("robot/+/telemetry", qos=0)
            client.subscribe("robot/+/events",    qos=1)
        else:
            logger.error(f"MQTT bridge connection failed: rc={rc}")

    def _on_message(self, client, userdata, msg):
        if self._loop is None:
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        # Thread-safe push to asyncio queue
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (msg.topic, payload))

    async def _process(self):
        """Drain the queue and persist to DB."""
        while True:
            topic, payload = await self._queue.get()
            parts = topic.split("/")  # robot / <id> / telemetry|events
            if len(parts) != 3:
                continue
            _, robot_id, kind = parts

            try:
                async with AsyncSessionLocal() as db:
                    svc = FleetService(db)
                    if kind == "telemetry":
                        battery = payload.get("battery_level", 0)
                        position = payload.get("position", {"x": 0, "y": 0, "floor": 1})
                        status = payload.get("status", "idle")
                        firmware_version = payload.get("firmware_version")
                        await svc.update_telemetry(
                            robot_id=robot_id,
                            battery_level=battery,
                            position=position,
                            status=status,
                            firmware_version=firmware_version,
                        )
                        # Insert into TimescaleDB telemetry table
                        await _insert_telemetry(db, robot_id, battery, position, status, payload)
                        # Push real-time update to WebSocket clients via Redis pub/sub
                        if self._redis:
                            ws_msg = json.dumps({
                                "type": "telemetry_update",
                                "data": {
                                    "robot_id": robot_id,
                                    "status": status,
                                    "battery_level": battery,
                                    "position": position,
                                    "speed": payload.get("speed"),
                                    "mission_progress": payload.get("mission_progress"),
                                    "last_seen": datetime.now(timezone.utc).isoformat(),
                                }
                            })
                            await self._redis.publish("ws:updates", ws_msg)
                    elif kind == "events":
                        await _insert_event(db, robot_id, payload)
                        # Sync mission status when robot finishes
                        event_type = payload.get("event_type")
                        if event_type == "MissionCompleted":
                            mission_id = payload.get("data", {}).get("mission_id")
                            if mission_id and not str(mission_id).startswith("manual_"):
                                await _complete_mission(mission_id)
                        elif event_type == "OTACompleted":
                            job_id = payload.get("data", {}).get("job_id")
                            if job_id:
                                await _update_ota_job(job_id, "completed")
                        elif event_type == "OTADownloading":
                            job_id = payload.get("data", {}).get("job_id")
                            if job_id:
                                await _update_ota_job(job_id, "downloading")
                        elif event_type == "OTAApplying":
                            job_id = payload.get("data", {}).get("job_id")
                            if job_id:
                                await _update_ota_job(job_id, "applying")
                        elif event_type == "OTAFailed":
                            job_id = payload.get("data", {}).get("job_id")
                            error = payload.get("data", {}).get("error")
                            if job_id:
                                await _update_ota_job(job_id, "failed", error_message=error)
            except Exception as exc:
                logger.warning(f"MQTT bridge DB error [{robot_id}/{kind}]: {exc}")

    async def start(self):
        self._loop = asyncio.get_event_loop()
        self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        self.client.connect_async(MQTT_BROKER, MQTT_PORT)
        self.client.loop_start()
        await self._process()  # runs forever

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()


async def _insert_telemetry(
    db, robot_id: str, battery: float, position: dict, status: str, payload: dict
):
    from sqlalchemy import text
    await db.execute(
        text("""
            INSERT INTO telemetry
                (time, robot_id, battery_level, position_x, position_y, position_floor,
                 nav_status, speed, mission_progress)
            VALUES
                (NOW(), :robot_id, :battery, :px, :py, :floor,
                 :nav_status, :speed, :mission_progress)
        """),
        {
            "robot_id":         robot_id,
            "battery":          battery,
            "px":               position.get("x"),
            "py":               position.get("y"),
            "floor":            position.get("floor", 1),
            "nav_status":       status,
            "speed":            payload.get("speed"),
            "mission_progress": payload.get("mission_progress"),
        },
    )
    await db.commit()


async def _update_ota_job(job_id: str, status: str, error_message: str | None = None):
    """Call ota-service to update an OTA job status."""
    import httpx
    body: dict = {"status": status}
    if error_message:
        body["error_message"] = error_message
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{OTA_SERVICE_URL}/api/v1/ota/jobs/{job_id}",
                json=body,
            )
            if resp.status_code == 200:
                logger.info(f"OTA job {job_id} → {status}")
            else:
                logger.warning(f"OTA job update returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Failed to update OTA job {job_id}: {e}")


async def _complete_mission(mission_id: str):
    """Call mission-service to mark a mission as completed."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{MISSION_SERVICE_URL}/api/v1/missions/{mission_id}",
                json={"status": "completed", "coverage_pct": 100.0},
            )
            if resp.status_code == 200:
                logger.info(f"Mission {mission_id} marked completed")
            else:
                logger.warning(f"Mission update returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Failed to complete mission {mission_id}: {e}")


async def _insert_event(db, robot_id: str, payload: dict):
    from sqlalchemy import text
    await db.execute(
        text("""
            INSERT INTO events (robot_id, event_type, severity, payload)
            VALUES (:robot_id, :event_type, :severity, CAST(:payload AS jsonb))
        """),
        {
            "robot_id":   robot_id,
            "event_type": payload.get("event_type", "unknown"),
            "severity":   payload.get("severity", "info"),
            "payload":    json.dumps(payload.get("data", {})),
        },
    )
    await db.commit()
