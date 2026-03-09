import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import paho.mqtt.client as mqtt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import FirmwareORM, OTAJobORM
from src.models.ota import (
    FirmwareCreate,
    FirmwareResponse,
    OTAJobCreate,
    OTAJobResponse,
)

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

SAFE_ROBOT_STATUSES = {"docked", "idle"}


def _mqtt_publish(topic: str, payload: dict, qos: int = 1) -> None:
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)
    client.publish(topic, json.dumps(payload), qos=qos)
    client.disconnect()


class OTAService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_firmware(self, data: FirmwareCreate) -> FirmwareResponse:
        fw = FirmwareORM(**data.model_dump())
        self.db.add(fw)
        await self.db.commit()
        await self.db.refresh(fw)
        return FirmwareResponse.model_validate(fw)

    async def list_firmware(self) -> list[FirmwareResponse]:
        result = await self.db.execute(
            select(FirmwareORM).order_by(FirmwareORM.uploaded_at.desc())
        )
        fws = result.scalars().all()
        return [FirmwareResponse.model_validate(f) for f in fws]

    async def create_jobs(self, data: OTAJobCreate) -> list[OTAJobResponse]:
        result = await self.db.execute(
            select(FirmwareORM).where(FirmwareORM.id == data.firmware_id)
        )
        fw = result.scalar_one_or_none()
        if fw is None:
            raise ValueError(f"Firmware '{data.firmware_id}' not found")

        # Import here to avoid circular dependency concerns with robot table
        from sqlalchemy import text
        jobs_created: list[OTAJobResponse] = []

        for robot_id_str in data.robot_ids:
            # Safety check: only create job if robot is docked or idle
            robot_result = await self.db.execute(
                text("SELECT status FROM robots WHERE robot_id = :rid OR id::text = :rid LIMIT 1"),
                {"rid": robot_id_str},
            )
            robot_row = robot_result.mappings().first()
            if robot_row is None:
                logger.warning("Robot '%s' not found, skipping OTA job", robot_id_str)
                continue
            if robot_row["status"] not in SAFE_ROBOT_STATUSES:
                logger.warning(
                    "Robot '%s' status '%s' is not safe for OTA, skipping",
                    robot_id_str,
                    robot_row["status"],
                )
                continue

            # Resolve UUID for robot
            uuid_result = await self.db.execute(
                text("SELECT id FROM robots WHERE robot_id = :rid OR id::text = :rid LIMIT 1"),
                {"rid": robot_id_str},
            )
            uuid_row = uuid_result.mappings().first()
            robot_uuid = uuid_row["id"] if uuid_row else robot_id_str

            job = OTAJobORM(
                firmware_id=fw.id,
                robot_id=robot_uuid,
                strategy=data.strategy,
                status="pending",
            )
            self.db.add(job)
            await self.db.flush()

            mqtt_payload = {
                "job_id": str(job.id),
                "firmware_id": str(fw.id),
                "version": fw.version,
                "s3_key": fw.s3_key,
                "checksum_sha256": fw.checksum_sha256,
                "strategy": data.strategy,
            }
            topic = f"robot/{robot_id_str}/ota"
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(None, _mqtt_publish, topic, mqtt_payload)
            except Exception as exc:
                logger.error("MQTT publish failed for robot '%s': %s", robot_id_str, exc)

            jobs_created.append(OTAJobResponse.model_validate(job))

        await self.db.commit()
        return jobs_created

    async def list_jobs(self, robot_id: Optional[str] = None) -> list[OTAJobResponse]:
        query = select(OTAJobORM)
        if robot_id:
            from sqlalchemy import text, or_
            uuid_result = await self.db.execute(
                text("SELECT id FROM robots WHERE robot_id = :rid OR id::text = :rid LIMIT 1"),
                {"rid": robot_id},
            )
            uuid_row = uuid_result.mappings().first()
            if uuid_row:
                query = query.where(OTAJobORM.robot_id == uuid_row["id"])
            else:
                return []
        query = query.order_by(OTAJobORM.created_at.desc())
        result = await self.db.execute(query)
        jobs = result.scalars().all()
        return [OTAJobResponse.model_validate(j) for j in jobs]

    async def update_job_status(self, job_id: UUID, status: str) -> Optional[OTAJobResponse]:
        result = await self.db.execute(
            select(OTAJobORM).where(OTAJobORM.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = status
        job.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(job)
        return OTAJobResponse.model_validate(job)
