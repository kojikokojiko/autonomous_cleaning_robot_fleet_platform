import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from typing import Optional
from uuid import UUID

import paho.mqtt.client as mqtt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import FirmwareORM, OTAJobORM
from src.dto.ota import (
    FirmwareCreate,
    FirmwareResponse,
    OTAJobCreate,
    OTAJobResponse,
)
from src.services import s3_client

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

SAFE_ROBOT_STATUSES = {"docked", "idle"}


def _mqtt_publish(topic: str, payload: dict, qos: int = 1) -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)
    client.publish(topic, json.dumps(payload), qos=qos)
    client.disconnect()


class OTAService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _firmware_content(version: str, config: dict) -> bytes:
        """Canonical JSON content that the robot will download and verify."""
        return json.dumps({"version": version, "config": config}, sort_keys=True).encode()

    async def create_firmware(self, data: FirmwareCreate) -> FirmwareResponse:
        config = data.config or {}
        content = self._firmware_content(data.version, config)
        computed_checksum = hashlib.sha256(content).hexdigest()

        # Upload to S3 (LocalStack locally, real S3 in production)
        s3_key = f"firmware/{data.version}/firmware.json"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, s3_client.upload, s3_key, content)

        fw_data = data.model_dump()
        fw_data["s3_key"]           = s3_key
        fw_data["checksum_sha256"]  = computed_checksum
        fw_data["file_size_bytes"]  = len(content)
        fw = FirmwareORM(**fw_data)
        self.db.add(fw)
        await self.db.commit()
        await self.db.refresh(fw)
        return FirmwareResponse.model_validate(fw)

    async def get_firmware(self, firmware_id: UUID) -> Optional[FirmwareResponse]:
        result = await self.db.execute(
            select(FirmwareORM).where(FirmwareORM.id == firmware_id)
        )
        fw = result.scalar_one_or_none()
        return FirmwareResponse.model_validate(fw) if fw else None

    async def download_firmware(self, firmware_id: UUID) -> Optional[bytes]:
        """Fetch firmware bytes from S3 and return to the caller (robot)."""
        fw = await self.get_firmware(firmware_id)
        if fw is None:
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, s3_client.download, fw.s3_key)

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
                "config": fw.config or {},
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
            from sqlalchemy import text
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

    async def update_job_status(
        self, job_id: UUID, status: str, error_message: Optional[str] = None
    ) -> Optional[OTAJobResponse]:
        result = await self.db.execute(
            select(OTAJobORM).where(OTAJobORM.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = status
        if error_message is not None:
            job.error_message = error_message
        if status in ("downloading", "applying"):
            job.attempts = (job.attempts or 0) + (1 if status == "downloading" else 0)
        job.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(job)
        return OTAJobResponse.model_validate(job)
