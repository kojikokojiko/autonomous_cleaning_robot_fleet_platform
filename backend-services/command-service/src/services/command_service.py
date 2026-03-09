import asyncio
import json
import logging
import os
from typing import Optional
from uuid import UUID

import paho.mqtt.client as mqtt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import CommandORM
from src.models.command import CommandCreate, CommandResponse

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

ALLOWED_COMMANDS = {"start_mission", "pause_mission", "return_to_dock", "emergency_stop"}


def _mqtt_publish(topic: str, payload: dict, qos: int = 1) -> None:
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)
    client.publish(topic, json.dumps(payload), qos=qos)
    client.disconnect()


class CommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def issue_command(self, data: CommandCreate) -> CommandResponse:
        if data.command_type not in ALLOWED_COMMANDS:
            raise ValueError(f"Unknown command type: {data.command_type}")

        payload = data.payload or {}
        if data.command_type == "emergency_stop":
            payload["critical"] = True

        cmd = CommandORM(
            robot_id=data.robot_id,
            command_type=data.command_type,
            payload=payload,
            issued_by=data.issued_by,
            status="pending",
        )
        self.db.add(cmd)
        await self.db.commit()
        await self.db.refresh(cmd)

        topic = f"robot/{data.robot_id}/command"
        mqtt_payload = {
            "command_id": str(cmd.id),
            "command_type": data.command_type,
            "payload": payload,
        }
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, _mqtt_publish, topic, mqtt_payload)
            cmd.status = "sent"
        except Exception as exc:
            logger.error("MQTT publish failed: %s", exc)
            cmd.status = "failed"

        await self.db.commit()
        await self.db.refresh(cmd)
        return CommandResponse.model_validate(cmd)

    async def get_command(self, command_id: UUID) -> Optional[CommandResponse]:
        result = await self.db.execute(
            select(CommandORM).where(CommandORM.id == command_id)
        )
        cmd = result.scalar_one_or_none()
        if cmd is None:
            return None
        return CommandResponse.model_validate(cmd)

    async def list_commands(
        self,
        robot_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[CommandResponse]:
        query = select(CommandORM)
        if robot_id:
            query = query.where(CommandORM.robot_id == robot_id)
        if status:
            query = query.where(CommandORM.status == status)
        query = query.order_by(CommandORM.issued_at.desc()).limit(limit)

        result = await self.db.execute(query)
        cmds = result.scalars().all()
        return [CommandResponse.model_validate(c) for c in cmds]
