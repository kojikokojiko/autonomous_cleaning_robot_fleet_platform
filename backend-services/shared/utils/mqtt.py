import os
import json
import logging
from typing import Callable, Optional
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


class MQTTClient:
    """Shared MQTT client wrapper for backend services."""

    def __init__(self, client_id: str, clean_session: bool = False):
        self.client = mqtt.Client(client_id=client_id, clean_session=clean_session)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self._subscriptions: dict[str, Callable] = {}

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("MQTT connected")
            for topic in self._subscriptions:
                client.subscribe(topic, qos=1)
        else:
            logger.error(f"MQTT connection failed: rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect: rc={rc}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            payload = msg.payload.decode()

        for pattern, handler in self._subscriptions.items():
            if mqtt.topic_matches_sub(pattern, topic):
                handler(topic, payload)

    def connect(self):
        self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        self.client.loop_start()

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def subscribe(self, topic: str, handler: Callable):
        self._subscriptions[topic] = handler
        if self.client.is_connected():
            self.client.subscribe(topic, qos=1)

    def publish(self, topic: str, payload: dict, qos: int = 1):
        self.client.publish(topic, json.dumps(payload), qos=qos)


# Topic helpers
def telemetry_topic(robot_id: str) -> str:
    return f"robot/{robot_id}/telemetry"

def command_topic(robot_id: str) -> str:
    return f"robot/{robot_id}/command"

def command_ack_topic(robot_id: str) -> str:
    return f"robot/{robot_id}/command/ack"

def events_topic(robot_id: str) -> str:
    return f"robot/{robot_id}/events"

def mission_topic(robot_id: str) -> str:
    return f"robot/{robot_id}/mission"

def ota_topic(robot_id: str) -> str:
    return f"robot/{robot_id}/ota"
