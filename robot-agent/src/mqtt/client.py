"""
MQTT Client for RobotOps robot agent.

- Maintains persistent session (clean_session=False) for command/event topics
- Telemetry: QoS 0 (high-frequency, loss acceptable)
- Commands/Events/OTA: QoS 1 (guaranteed delivery)
"""
import json
import logging
import threading
from typing import Callable, Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class RobotMQTTClient:
    def __init__(
        self,
        robot_id: str,
        broker: str = "localhost",
        port: int = 1883,
        keepalive: int = 60,
        on_command: Optional[Callable] = None,
        on_mission: Optional[Callable] = None,
        on_ota: Optional[Callable] = None,
    ):
        self.robot_id = robot_id
        self.broker = broker
        self.port = port
        self.on_command = on_command
        self.on_mission = on_mission
        self.on_ota = on_ota

        # Persistent session: robot receives queued commands after reconnect
        self.client = mqtt.Client(
            client_id=robot_id,
            clean_session=False,
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self._connected = threading.Event()

    # ------------------------------------------------------------------ Topics
    @property
    def _telemetry_topic(self): return f"robot/{self.robot_id}/telemetry"
    @property
    def _events_topic(self):    return f"robot/{self.robot_id}/events"
    @property
    def _command_topic(self):   return f"robot/{self.robot_id}/command"
    @property
    def _command_ack_topic(self): return f"robot/{self.robot_id}/command/ack"
    @property
    def _mission_topic(self):   return f"robot/{self.robot_id}/mission"
    @property
    def _ota_topic(self):       return f"robot/{self.robot_id}/ota"

    # ---------------------------------------------------------------- Lifecycle
    def connect(self):
        self.client.connect(self.broker, self.port, keepalive=60)
        self.client.loop_start()
        self._connected.wait(timeout=10)

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    # ----------------------------------------------------------- MQTT callbacks
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"[{self.robot_id}] MQTT connected to {self.broker}:{self.port}")
            client.subscribe(self._command_topic, qos=1)
            client.subscribe(self._mission_topic, qos=1)
            client.subscribe(self._ota_topic, qos=1)
            self._connected.set()
        else:
            logger.error(f"[{self.robot_id}] MQTT connection failed: rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning(f"[{self.robot_id}] MQTT unexpected disconnect: rc={rc}")
        self._connected.clear()

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except json.JSONDecodeError:
            payload = msg.payload.decode("utf-8")

        if msg.topic == self._command_topic and self.on_command:
            self.on_command(payload)
        elif msg.topic == self._mission_topic and self.on_mission:
            self.on_mission(payload)
        elif msg.topic == self._ota_topic and self.on_ota:
            self.on_ota(payload)

    # --------------------------------------------------------------- Publishing
    def publish_telemetry(self, payload: dict):
        self.client.publish(
            self._telemetry_topic,
            json.dumps(payload),
            qos=0,  # high-frequency, loss acceptable
        )

    def publish_event(self, event_type: str, data: dict, severity: str = "info"):
        payload = {
            "robot_id": self.robot_id,
            "event_type": event_type,
            "severity": severity,
            "data": data,
        }
        self.client.publish(self._events_topic, json.dumps(payload), qos=1)
        logger.info(f"[{self.robot_id}] Event: {event_type}")

    def publish_command_ack(self, command_id: str, success: bool, message: str = ""):
        payload = {
            "robot_id": self.robot_id,
            "command_id": command_id,
            "success": success,
            "message": message,
        }
        self.client.publish(self._command_ack_topic, json.dumps(payload), qos=1)
        logger.info(f"[{self.robot_id}] Command ACK: {command_id} success={success}")
