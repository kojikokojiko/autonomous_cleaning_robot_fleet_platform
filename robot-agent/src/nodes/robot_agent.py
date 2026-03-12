"""
Robot Agent - core node that bridges ROS2 (or simulator) ↔ cloud.

Responsibilities:
  - Publish telemetry every N seconds (QoS 0)
  - Receive and ACK commands (QoS 1)
  - Publish robot events (QoS 1)
  - Handle OTA update notifications
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Optional
import urllib.request

from src.mqtt.client import RobotMQTTClient
from src.nodes.state import RobotState, RobotStatus

logger = logging.getLogger(__name__)

OTA_SERVICE_URL   = os.getenv("OTA_SERVICE_URL", "http://localhost:8080")
ROBOT_CONFIG_DIR  = Path.home() / ".robot_configs"

ALLOWED_COMMANDS = {"start_mission", "pause_mission", "return_to_dock", "emergency_stop"}

BATTERY_DRAIN_PER_CYCLE  = 0.05   # % per telemetry cycle when cleaning
BATTERY_CHARGE_PER_CYCLE = 0.2    # % per telemetry cycle when docked
BATTERY_LOW_THRESHOLD    = 20.0
BATTERY_CRITICAL_THRESHOLD = 10.0
STEP_PER_CYCLE           = 0.5    # metres per telemetry cycle
ROW_SPACING              = 1.0    # metres between lawnmower rows
DOCK_ARRIVE_THRESHOLD    = 0.3    # metres — "close enough" to be docked

# Charging dock positions (must match dashboard FleetMap DOCKS)
DOCK_POSITIONS = [
    (1.0,  17.5),
    (2.5,  17.5),
]


# ── Zone definitions (must match dashboard floor plan) ────────────────────────
@dataclass
class Zone:
    name: str
    x_min: float
    x_max: float
    z_min: float
    z_max: float


ZONES = [
    # Each zone is inset ≥1 m from the visual wall so the robot body (r=0.38 m)
    # never visually overlaps with wall geometry.
    Zone("lobby",     1.0,  5.0,  1.0,  7.8),
    Zone("zone_a",    7.0, 24.0,  1.0,  7.8),
    Zone("corridor",  1.0, 24.0,  9.7, 10.3),
    Zone("zone_b",    1.0, 12.0, 12.0, 18.8),
    Zone("zone_c",   14.0, 24.0, 12.0, 18.8),
]


def zone_for(x: float, z: float) -> Zone:
    """Return the zone that contains (x, z), or the nearest zone."""
    for zone in ZONES:
        if zone.x_min <= x <= zone.x_max and zone.z_min <= z <= zone.z_max:
            return zone
    # fallback: pick closest zone centre
    def dist(zone: Zone) -> float:
        cx = (zone.x_min + zone.x_max) / 2
        cz = (zone.z_min + zone.z_max) / 2
        return (x - cx) ** 2 + (z - cz) ** 2
    return min(ZONES, key=dist)


# ── Waypoint navigation ───────────────────────────────────────────────────────
# Corridor passage points — safe entry/exit for each zone via the corridor.
# These keep the robot on the open floor and away from interior walls.
_NAV_ENTRY: dict[str, tuple[float, float]] = {
    "lobby":    (3.0,  9.5),   # lobby ↔ corridor
    "zone_a":   (15.0, 9.5),   # zone_a ↔ corridor
    "zone_b":   (6.0,  10.5),  # zone_b ↔ corridor
    "zone_c":   (18.0, 10.5),  # zone_c ↔ corridor
    "corridor": (12.0, 10.0),  # corridor midpoint (fallback)
}
_NORTH = {"lobby", "zone_a"}
_SOUTH = {"zone_b", "zone_c"}


def compute_nav_path(
    x1: float, z1: float,
    x2: float, z2: float,
) -> list[tuple[float, float]]:
    """Return a wall-safe waypoint path from (x1,z1) to (x2,z2).

    Interior walls that require corridor detours:
      - x=6  wall  (lobby | zone_a),   z=0–9
      - x=13 wall  (zone_b | zone_c),  z=10.5–20
    Any cross-zone move routes through corridor passage points.
    """
    start = zone_for(x1, z1).name
    end   = zone_for(x2, z2).name

    if start == end:
        return [(x2, z2)]

    wps: list[tuple[float, float]] = []

    if start == "corridor":
        wps.append(_NAV_ENTRY.get(end, (x2, z2)))
    elif end == "corridor":
        wps.append(_NAV_ENTRY.get(start, (x1, z1)))
    else:
        # Always go through corridor when changing zones
        wps.append(_NAV_ENTRY[start])
        if (_NORTH.__contains__(start) and _SOUTH.__contains__(end)) or \
           (_SOUTH.__contains__(start) and _NORTH.__contains__(end)) or \
           (start in _NORTH and end in _NORTH) or \
           (start in _SOUTH and end in _SOUTH):
            wps.append(_NAV_ENTRY[end])

    wps.append((x2, z2))
    return wps


# ── Lawnmower state ───────────────────────────────────────────────────────────
@dataclass
class LawnmowerState:
    zone: Zone
    direction: int = 1   # +1 = moving in +x direction, -1 = moving in -x direction


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
        self._step_per_cycle = STEP_PER_CYCLE
        self._firmware_version: Optional[str] = None
        self._mission_id: Optional[str] = None
        self._lawnmower: Optional[LawnmowerState] = None
        self._dock_target: Optional[tuple[float, float]] = None
        self._transit_path: list[tuple[float, float]] = []  # waypoints to zone start
        self._target_zone: Optional[Zone] = None            # zone to clean after arriving

        self.mqtt = RobotMQTTClient(
            robot_id=robot_id,
            broker=mqtt_broker,
            port=mqtt_port,
            on_command=self._handle_command,
            on_mission=self._handle_mission,
            on_ota=self._handle_ota,
        )
        self._load_config()  # restore persisted config from previous OTA

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
            if self._transit_path:
                # Navigate waypoint-by-waypoint to avoid interior walls
                tx, tz = self._transit_path[0]
                dx = tx - self.state.position_x
                dz = tz - self.state.position_y
                dist = (dx ** 2 + dz ** 2) ** 0.5
                if dist <= DOCK_ARRIVE_THRESHOLD:
                    self.state.position_x = tx
                    self.state.position_y = tz
                    self._transit_path.pop(0)
                    if not self._transit_path and self._target_zone:
                        # All waypoints done — begin lawnmower in target zone
                        self._lawnmower = LawnmowerState(zone=self._target_zone)
                        logger.info(
                            f"[{self.robot_id}] Arrived at {self._target_zone.name},"
                            f" starting lawnmower"
                        )
                        self._target_zone = None
                else:
                    step = min(self._step_per_cycle, dist)
                    self.state.position_x += (dx / dist) * step
                    self.state.position_y += (dz / dist) * step
                self.state.speed = self._step_per_cycle
            else:
                self._advance_lawnmower()
                self.state.speed = self._step_per_cycle
                self.state.mission_progress = min(
                    100.0, (self.state.mission_progress or 0.0) + 0.5
                )

        elif self.state.status == RobotStatus.CHARGING:
            if self._transit_path:
                # Follow wall-safe waypoints back to dock
                tx, tz = self._transit_path[0]
                dx = tx - self.state.position_x
                dz = tz - self.state.position_y
                dist = (dx ** 2 + dz ** 2) ** 0.5
                if dist <= DOCK_ARRIVE_THRESHOLD:
                    self.state.position_x = tx
                    self.state.position_y = tz
                    self._transit_path.pop(0)
                    if not self._transit_path:
                        # Last waypoint was the dock — arrived
                        self.state.speed = 0.0
                        self._dock_target = None
                        self.state.status = RobotStatus.DOCKED
                        logger.info(f"[{self.robot_id}] Arrived at dock ({tx:.1f}, {tz:.1f})")
                else:
                    step = min(self._step_per_cycle, dist)
                    self.state.position_x += (dx / dist) * step
                    self.state.position_y += (dz / dist) * step
                    self.state.speed = self._step_per_cycle
            elif self._dock_target:
                # Fallback: direct approach (no path computed)
                tx, tz = self._dock_target
                dx = tx - self.state.position_x
                dz = tz - self.state.position_y
                dist = (dx ** 2 + dz ** 2) ** 0.5
                if dist <= DOCK_ARRIVE_THRESHOLD:
                    self.state.position_x = tx
                    self.state.position_y = tz
                    self.state.speed = 0.0
                    self._dock_target = None
                    self.state.status = RobotStatus.DOCKED
                    logger.info(f"[{self.robot_id}] Arrived at dock ({tx:.1f}, {tz:.1f})")
                else:
                    step = min(self._step_per_cycle, dist)
                    self.state.position_x += (dx / dist) * step
                    self.state.position_y += (dz / dist) * step
                    self.state.speed = self._step_per_cycle
            else:
                self.state.speed = 0.0

        elif self.state.status == RobotStatus.DOCKED:
            self.state.battery_level = min(
                100.0, self.state.battery_level + BATTERY_CHARGE_PER_CYCLE
            )
            self.state.speed = 0.0
            if self.state.battery_level >= 100.0:
                self.state.status = RobotStatus.IDLE
                logger.info(f"[{self.robot_id}] Battery fully charged — transitioning to idle")

        elif self.state.status == RobotStatus.IDLE:
            self.state.speed = 0.0

    def _advance_lawnmower(self):
        """Move robot one step in the lawnmower pattern, staying within zone."""
        if self._lawnmower is None:
            # Initialise lawnmower for the zone the robot currently occupies
            zone = zone_for(self.state.position_x, self.state.position_y)
            self._lawnmower = LawnmowerState(zone=zone)
            # Snap to zone start corner
            self.state.position_x = zone.x_min
            self.state.position_y = zone.z_min
            logger.info(f"[{self.robot_id}] Lawnmower started in {zone.name} "
                        f"({zone.x_min:.0f}-{zone.x_max:.0f}, {zone.z_min:.0f}-{zone.z_max:.0f})")
            return

        lm = self._lawnmower
        zone = lm.zone

        # Advance along x
        new_x = self.state.position_x + lm.direction * self._step_per_cycle

        if lm.direction == 1 and new_x >= zone.x_max:
            # Hit right wall → clamp, step one row in z, reverse
            self.state.position_x = zone.x_max
            new_z = self.state.position_y + ROW_SPACING
            lm.direction = -1
            if new_z > zone.z_max:
                # All rows covered — zone is fully cleaned
                logger.info(f"[{self.robot_id}] Lawnmower finished zone {zone.name}")
                self.state.mission_progress = 100.0
                return
            self.state.position_y = new_z
        elif lm.direction == -1 and new_x <= zone.x_min:
            # Hit left wall → clamp, step one row in z, reverse
            self.state.position_x = zone.x_min
            new_z = self.state.position_y + ROW_SPACING
            lm.direction = 1
            if new_z > zone.z_max:
                # All rows covered — zone is fully cleaned
                logger.info(f"[{self.robot_id}] Lawnmower finished zone {zone.name}")
                self.state.mission_progress = 100.0
                return
            self.state.position_y = new_z
        else:
            self.state.position_x = new_x

        # Safety clamp
        self.state.position_y = min(self.state.position_y, zone.z_max)

    def _publish_telemetry(self):
        payload = {
            "robot_id":         self.robot_id,
            "firmware_version": self._firmware_version,
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "battery_level":    round(self.state.battery_level, 2),
            "position": {
                "x":     round(self.state.position_x, 3),
                "y":     round(self.state.position_y, 3),
                "floor": self.state.floor,
            },
            "status":           self.state.status.value,
            "nav_status":       self.state.nav_status,
            "motor_load_left":  round(self.state.motor_load_left, 3),
            "motor_load_right": round(self.state.motor_load_right, 3),
            "sensor_health":    self.state.sensor_health,
            "mission_id":       self._mission_id,
            "mission_progress": round(self.state.mission_progress or 0.0, 2),
            "speed":            round(self.state.speed, 3),
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
                self._cmd_return_to_dock()

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
            self._lawnmower = None

    # -------------------------------------------------------------- Handlers
    def _handle_command(self, payload: dict):
        command_id   = payload.get("command_id", "unknown")
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
        inner = payload.get("payload", {})
        mission_id = inner.get("mission_id") or payload.get("mission_id")
        zone_name  = inner.get("zone")       or payload.get("zone")

        self._mission_id = mission_id
        self.state.status = RobotStatus.CLEANING
        self.state.mission_progress = 0.0
        self._lawnmower = None
        self._transit_path = []
        self._target_zone = None

        if zone_name:
            target = next((z for z in ZONES if z.name == zone_name), None)
            if target:
                current_zone = zone_for(self.state.position_x, self.state.position_y)
                if current_zone.name == zone_name:
                    logger.info(f"[{self.robot_id}] Already in {zone_name}, starting lawnmower")
                else:
                    path = compute_nav_path(
                        self.state.position_x, self.state.position_y,
                        target.x_min, target.z_min,
                    )
                    self._transit_path = path
                    self._target_zone = target
                    logger.info(
                        f"[{self.robot_id}] Navigating to {zone_name} "
                        f"via {len(path)} waypoints: {path}"
                    )
            else:
                logger.warning(f"[{self.robot_id}] Unknown zone '{zone_name}', using current position")  # noqa: E501

        self.mqtt.publish_event(
            "MissionStarted",
            {"robot_id": self.robot_id, "mission_id": mission_id},
        )

    def _cmd_pause(self):
        if self.state.status == RobotStatus.CLEANING:
            self.state.status = RobotStatus.IDLE

    def _cmd_return_to_dock(self):
        # Pick the nearest dock and compute a wall-safe path
        rx, rz = self.state.position_x, self.state.position_y
        nearest = min(DOCK_POSITIONS, key=lambda d: (d[0]-rx)**2 + (d[1]-rz)**2)
        path = compute_nav_path(rx, rz, nearest[0], nearest[1])
        self._dock_target  = nearest
        self._transit_path = path   # wall-safe waypoints ending at dock
        self._lawnmower    = None
        self._target_zone  = None
        self.state.status = RobotStatus.CHARGING   # CHARGING = en-route to dock
        logger.info(f"[{self.robot_id}] Returning to dock at {nearest} via {len(path)} waypoints: {path}")  # noqa: E501

    def _cmd_emergency_stop(self):
        logger.warning(f"[{self.robot_id}] EMERGENCY STOP executed")
        self.state.status  = RobotStatus.IDLE
        self.state.speed   = 0.0
        self._lawnmower    = None
        self._transit_path = []
        self._target_zone  = None
        self.mqtt.publish_event(
            "EmergencyStop",
            {"robot_id": self.robot_id},
            severity="critical",
        )

    def _handle_mission(self, payload: dict):
        logger.info(f"[{self.robot_id}] Mission received: {payload}")

    # --------------------------------------------------------- Config persistence
    def _config_path(self) -> Path:
        ROBOT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return ROBOT_CONFIG_DIR / f"{self.robot_id}.json"

    def _load_config(self):
        """On startup: restore parameters from the last successful OTA."""
        path = self._config_path()
        if not path.exists():
            return
        try:
            cfg = json.loads(path.read_text())
            self._apply_config(cfg)
            if "_version" in cfg:
                self._firmware_version = cfg["_version"]
            logger.info(f"[{self.robot_id}] Restored config from disk: {cfg}")
        except Exception as exc:
            logger.warning(f"[{self.robot_id}] Could not load persisted config: {exc}")

    def _save_config(self, config: dict, version: Optional[str] = None):
        """Persist config to disk so it survives process restarts."""
        path = self._config_path()
        save_data = {**config}
        if version:
            save_data["_version"] = version
        path.write_text(json.dumps(save_data, indent=2))
        logger.info(f"[{self.robot_id}] Config persisted → {path}")

    def _apply_config(self, config: dict):
        """Apply config values to the running instance."""
        if "step_per_cycle" in config:
            old = self._step_per_cycle
            self._step_per_cycle = float(config["step_per_cycle"])
            logger.info(f"[{self.robot_id}] step_per_cycle: {old:.2f} → {self._step_per_cycle:.2f}")

    # ---------------------------------------------------------------- OTA flow
    def _handle_ota(self, payload: dict):
        logger.info(f"[{self.robot_id}] OTA notification received: {payload}")
        if self.state.status not in (RobotStatus.DOCKED, RobotStatus.IDLE):
            logger.info(f"[{self.robot_id}] OTA deferred (robot is {self.state.status.value})")
            return

        job_id            = payload.get("job_id")
        version           = payload.get("version")
        firmware_id       = payload.get("firmware_id")
        expected_checksum = payload.get("checksum_sha256", "")

        # Capture current config for rollback
        rollback_config = {"step_per_cycle": self._step_per_cycle}

        self.state.status = RobotStatus.OTA_UPDATE
        self.mqtt.publish_event(
            "OTAStarted",
            {"robot_id": self.robot_id, "version": version, "job_id": job_id},
        )

        def _run():
            try:
                # ── Phase 1: Download ──────────────────────────────────────────
                logger.info(f"[{self.robot_id}] OTA [1/4] Downloading firmware {firmware_id}…")
                self.mqtt.publish_event(
                    "OTADownloading",
                    {"robot_id": self.robot_id, "job_id": job_id},
                )
                url = f"{OTA_SERVICE_URL}/api/v1/ota/firmware/{firmware_id}/download"
                with urllib.request.urlopen(url, timeout=15) as resp:
                    content_bytes = resp.read()
                logger.info(f"[{self.robot_id}] OTA downloaded {len(content_bytes)} bytes")

                # ── Phase 2: Verify checksum ───────────────────────────────────
                actual_checksum = hashlib.sha256(content_bytes).hexdigest()
                if expected_checksum and actual_checksum != expected_checksum:
                    raise ValueError(
                        f"Checksum mismatch: expected={expected_checksum[:12]}… "
                        f"got={actual_checksum[:12]}…"
                    )
                logger.info(f"[{self.robot_id}] OTA [2/4] Checksum OK ✓ ({actual_checksum[:16]}…)")

                # ── Phase 3: Parse & apply ─────────────────────────────────────
                downloaded = json.loads(content_bytes.decode())
                new_config = downloaded.get("config", {})
                logger.info(f"[{self.robot_id}] OTA [3/4] Applying config: {new_config}")
                self.mqtt.publish_event(
                    "OTAApplying",
                    {"robot_id": self.robot_id, "job_id": job_id},
                )
                time.sleep(1.0)  # simulate flash write latency
                self._apply_config(new_config)

                # ── Phase 4: Persist to disk ───────────────────────────────────
                self._save_config(new_config, version=version)
                self._firmware_version = version
                logger.info(f"[{self.robot_id}] OTA [4/4] Config persisted to disk (version={version})")  # noqa: E501

                # ── Complete ───────────────────────────────────────────────────
                self.state.status = RobotStatus.IDLE
                self.mqtt.publish_event(
                    "OTACompleted",
                    {"robot_id": self.robot_id, "version": version, "job_id": job_id},
                )
                logger.info(f"[{self.robot_id}] OTA completed successfully (job={job_id})")

            except Exception as exc:
                logger.error(f"[{self.robot_id}] OTA failed: {exc}")
                # ── Rollback ───────────────────────────────────────────────────
                logger.warning(f"[{self.robot_id}] OTA rolling back to {rollback_config}")
                self._apply_config(rollback_config)
                self.state.status = RobotStatus.IDLE
                self.mqtt.publish_event(
                    "OTAFailed",
                    {"robot_id": self.robot_id, "version": version,
                     "job_id": job_id, "error": str(exc)},
                )

        threading.Thread(target=_run, daemon=True, name=f"{self.robot_id}-ota").start()
