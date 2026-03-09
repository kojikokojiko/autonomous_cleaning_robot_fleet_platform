"""
Robot Agent - core node that bridges ROS2 (or simulator) ↔ cloud.

Responsibilities:
  - Publish telemetry every N seconds (QoS 0)
  - Receive and ACK commands (QoS 1)
  - Publish robot events (QoS 1)
  - Handle OTA update notifications
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from src.mqtt.client import RobotMQTTClient
from src.nodes.state import RobotState, RobotStatus

logger = logging.getLogger(__name__)

BATTERY_DRAIN_PER_CYCLE = 0.05   # % per telemetry cycle when cleaning
BATTERY_CHARGE_PER_CYCLE = 0.2   # % per telemetry cycle when docked
BATTERY_LOW_THRESHOLD = 20.0
BATTERY_CRITICAL_THRESHOLD = 10.0


class RobotAgent:
    def __init__(
        self,
        robot_id: str,
        mqtt_broker: str = "localhost",
        mqtt_port: int = 1883,
        telemetry_interval: float = 2.0,
        initial_state: Optional[RobotState] = None,
    ):
        self.robot_id = robot_id
        self.telemetry_interval = telemetry_interval
        self.state = initial_state or RobotState(robot_id=robot_id)
        self._running = False
        self._mission_id: Optional[str] = None

        self.mqtt = RobotMQTTClient(
            robot_id=robot_id,
            broker=mqtt_broker,
            port=mqtt_port,
            on_command=self._handle_command,
            on_mission=self._handle_mission,
            on_ota=self._handle_ota,
        )

    def start(self):
        self._running = True
        self.mqtt.connect()
        logger.info(f"[{self.robot_id}] Robot agent started")

        telemetry_thread = threading.Thread(
            target=self._telemetry_loop, daemon=True, name=f"{self.robot_id}-telemetry"
        )
        telemetry_thread.start()

    def stop(self):
        self._running = False
        self.mqtt.disconnect()
        logger.info(f"[{self.robot_id}] Robot agent stopped")

    # --------------------------------------------------------------- Telemetry
    def _telemetry_loop(self):
        while self._running:
            self._simulate_state()
            self._publish_telemetry()
            self._check_and_emit_events()
            time.sleep(self.telemetry_interval)

    def _simulate_state(self):
        """Simulate robot physics and battery dynamics."""
        if self.state.status == RobotStatus.CLEANING:
            self.state.battery_level = max(
                0.0, self.state.battery_level - BATTERY_DRAIN_PER_CYCLE
            )
            # Move robot in a lawnmower pattern
            self.state.position_x += 0.1
            if self.state.position_x > 20:
                self.state.position_x = 0
                self.state.position_y += 0.5
            self.state.speed = 0.3
            self.state.mission_progress = min(
                100.0, (self.state.mission_progress or 0.0) + 0.5
            )

        elif self.state.status in (RobotStatus.CHARGING, RobotStatus.DOCKED):
            self.state.battery_level = min(
                100.0, self.state.battery_level + BATTERY_CHARGE_PER_CYCLE
            )
            self.state.speed = 0.0

        elif self.state.status == RobotStatus.IDLE:
            self.state.speed = 0.0

    def _publish_telemetry(self):
        payload = {
            "robot_id": self.robot_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "battery_level": round(self.state.battery_level, 2),
            "position": {
                "x": round(self.state.position_x, 3),
                "y": round(self.state.position_y, 3),
                "floor": self.state.floor,
            },
            "nav_status": self.state.nav_status,
            "motor_load_left": round(self.state.motor_load_left, 3),
            "motor_load_right": round(self.state.motor_load_right, 3),
            "sensor_health": self.state.sensor_health,
            "mission_id": self._mission_id,
            "mission_progress": round(self.state.mission_progress or 0.0, 2),
            "speed": round(self.state.speed, 3),
        }
        self.mqtt.publish_telemetry(payload)

    # ----------------------------------------------------------- Event checks
    def _check_and_emit_events(self):
        if self.state.battery_level <= BATTERY_CRITICAL_THRESHOLD:
            self.mqtt.publish_event(
                "RobotBatteryLow",
                {"robot_id": self.robot_id, "battery_level": self.state.battery_level},
                severity="critical",
            )
            if self.state.status == RobotStatus.CLEANING:
                logger.warning(f"[{self.robot_id}] Critical battery - returning to dock")
                self.state.status = RobotStatus.CHARGING

        elif (
            self.state.battery_level <= BATTERY_LOW_THRESHOLD
            and self.state.status == RobotStatus.CLEANING
        ):
            self.mqtt.publish_event(
                "RobotBatteryLow",
                {"robot_id": self.robot_id, "battery_level": self.state.battery_level},
                severity="warning",
            )

        if self.state.mission_progress and self.state.mission_progress >= 100.0:
            self.mqtt.publish_event(
                "MissionCompleted",
                {"robot_id": self.robot_id, "mission_id": self._mission_id},
                severity="info",
            )
            self.state.status = RobotStatus.IDLE
            self.state.mission_progress = 0.0
            self._mission_id = None

    # -------------------------------------------------------------- Handlers
    def _handle_command(self, payload: dict):
        command_id = payload.get("command_id", "unknown")
        command_type = payload.get("command_type", "")
        logger.info(f"[{self.robot_id}] Received command: {command_type} (id={command_id})")

        try:
            if command_type == "start_mission":
                self._cmd_start_mission(payload)
            elif command_type == "pause_mission":
                self._cmd_pause()
            elif command_type == "return_to_dock":
                self._cmd_return_to_dock()
            elif command_type == "emergency_stop":
                self._cmd_emergency_stop()
            else:
                logger.warning(f"[{self.robot_id}] Unknown command: {command_type}")
                self.mqtt.publish_command_ack(command_id, False, f"Unknown command: {command_type}")
                return

            self.mqtt.publish_command_ack(command_id, True)
        except Exception as e:
            logger.error(f"[{self.robot_id}] Command execution failed: {e}")
            self.mqtt.publish_command_ack(command_id, False, str(e))

    def _cmd_start_mission(self, payload: dict):
        mission_id = payload.get("payload", {}).get("mission_id") or payload.get("mission_id")
        self._mission_id = mission_id
        self.state.status = RobotStatus.CLEANING
        self.state.mission_progress = 0.0
        self.mqtt.publish_event(
            "MissionStarted",
            {"robot_id": self.robot_id, "mission_id": mission_id},
        )

    def _cmd_pause(self):
        if self.state.status == RobotStatus.CLEANING:
            self.state.status = RobotStatus.IDLE

    def _cmd_return_to_dock(self):
        self.state.status = RobotStatus.DOCKED
        self.state.speed = 0.0

    def _cmd_emergency_stop(self):
        logger.warning(f"[{self.robot_id}] EMERGENCY STOP executed")
        self.state.status = RobotStatus.IDLE
        self.state.speed = 0.0
        self.mqtt.publish_event(
            "EmergencyStop",
            {"robot_id": self.robot_id},
            severity="critical",
        )

    def _handle_mission(self, payload: dict):
        logger.info(f"[{self.robot_id}] Mission received: {payload}")

    def _handle_ota(self, payload: dict):
        logger.info(f"[{self.robot_id}] OTA update notification: {payload}")
        if self.state.status not in (RobotStatus.DOCKED, RobotStatus.IDLE):
            logger.info(f"[{self.robot_id}] OTA queued (robot is {self.state.status.value})")
            return
        # In production, this would trigger the actual update download
        self.state.status = RobotStatus.OTA_UPDATE
        self.mqtt.publish_event(
            "OTAStarted",
            {"robot_id": self.robot_id, "version": payload.get("version")},
        )
