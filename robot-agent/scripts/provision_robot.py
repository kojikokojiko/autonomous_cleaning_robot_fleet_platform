"""
Robot first-boot IoT provisioning — AWS IoT Fleet Provisioning by Claim.

Flow:
  1. If permanent cert already exists → already provisioned, exit 0
  2. Connect to AWS IoT Core with claim certificate (mTLS, port 8883)
  3. Call CreateKeysAndCertificate via MQTT ($aws/certificates/create/json)
  4. Register the robot via Fleet Provisioning template (creates Thing + attaches policy)
  5. Save permanent cert + private key to CERTS_DIR
  6. Save robot_id (thing name) to ROBOT_ID_FILE

Usage:
  python scripts/provision_robot.py --serial-number CLEANBOT_0001

Environment variables:
  IOT_ENDPOINT      — AWS IoT data endpoint (required)
                      e.g. xyz123.iot.ap-northeast-1.amazonaws.com
  IOT_TEMPLATE_NAME — Fleet Provisioning template name (default: robotops-dev-fleet-template)
  ROBOTOPS_CERTS_DIR — directory for certs (default: /etc/robotops/certs)
  ROBOTOPS_ID_FILE   — path to store robot_id (default: /etc/robotops/robot_id)
"""

import argparse
import json
import logging
import os
import sys
import threading
from pathlib import Path

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CERTS_DIR = Path(os.environ.get("ROBOTOPS_CERTS_DIR", "/etc/robotops/certs"))
ROBOT_ID_FILE = Path(os.environ.get("ROBOTOPS_ID_FILE", "/etc/robotops/robot_id"))

DEVICE_CERT = CERTS_DIR / "device.crt"
DEVICE_KEY  = CERTS_DIR / "device.key"
CLAIM_CERT  = CERTS_DIR / "claim.crt"
CLAIM_KEY   = CERTS_DIR / "claim.key"
ROOT_CA     = CERTS_DIR / "AmazonRootCA1.pem"

# ---------------------------------------------------------------------------
# AWS IoT config
# ---------------------------------------------------------------------------
IOT_PORT = 8883


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        logger.error(f"Required environment variable {name} is not set")
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# Fleet Provisioner
# ---------------------------------------------------------------------------
class FleetProvisioner:
    """
    Executes the Fleet Provisioning by Claim flow over MQTT.

    Step 1 — CreateKeysAndCertificate:
      Publish {}  → $aws/certificates/create/json
      Receive     ← $aws/certificates/create/json/accepted
                     {certificateId, certificatePem, privateKey, certificateOwnershipToken}

    Step 2 — RegisterThing:
      Publish {certificateOwnershipToken, parameters:{SerialNumber}}
              → $aws/provisioning-templates/{template}/provision/json
      Receive ← $aws/provisioning-templates/{template}/provision/json/accepted
                   {thingName, deviceConfiguration}
    """

    def __init__(self, serial_number: str, iot_endpoint: str, template_name: str):
        self.serial_number = serial_number
        self.iot_endpoint = iot_endpoint
        self.template_name = template_name

        self._cert_response: dict | None = None
        self._provision_result: dict | None = None
        self._error: str | None = None
        self._cert_event = threading.Event()
        self._provision_event = threading.Event()

    def provision(self) -> dict:
        """Run full provisioning flow. Returns {robot_id, cert_pem, private_key}."""
        client_id = f"provisioning-{self.serial_number}"
        client = mqtt.Client(client_id=client_id, clean_session=True)
        client.tls_set(
            ca_certs=str(ROOT_CA),
            certfile=str(CLAIM_CERT),
            keyfile=str(CLAIM_KEY),
        )
        client.on_connect = self._on_connect
        client.on_message = self._on_message

        logger.info(f"Connecting to {self.iot_endpoint}:{IOT_PORT} with claim certificate...")
        client.connect(self.iot_endpoint, IOT_PORT, keepalive=30)
        client.loop_start()

        try:
            # Step 1: request new certificate + private key
            logger.info("Step 1: Creating device certificate...")
            client.publish("$aws/certificates/create/json", json.dumps({}), qos=1)
            if not self._cert_event.wait(timeout=30):
                raise TimeoutError("Timed out waiting for certificate creation response")
            if self._error:
                raise RuntimeError(f"Certificate creation failed: {self._error}")

            # Step 2: register the robot (creates Thing, attaches cert + policy)
            logger.info(f"Step 2: Registering robot serial={self.serial_number}...")
            client.publish(
                f"$aws/provisioning-templates/{self.template_name}/provision/json",
                json.dumps({
                    "certificateOwnershipToken": self._cert_response["certificateOwnershipToken"],
                    "parameters": {"SerialNumber": self.serial_number},
                }),
                qos=1,
            )
            if not self._provision_event.wait(timeout=30):
                raise TimeoutError("Timed out waiting for provisioning response")
            if self._error:
                raise RuntimeError(f"Provisioning failed: {self._error}")

        finally:
            client.loop_stop()
            client.disconnect()

        return {
            "robot_id":   self._provision_result["thingName"],
            "cert_pem":   self._cert_response["certificatePem"],
            "private_key": self._cert_response["privateKey"],
        }

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            logger.error(f"MQTT connection failed: rc={rc}")
            return
        logger.info("Connected with claim certificate")
        client.subscribe("$aws/certificates/create/json/accepted", qos=1)
        client.subscribe("$aws/certificates/create/json/rejected", qos=1)
        client.subscribe(
            f"$aws/provisioning-templates/{self.template_name}/provision/json/accepted", qos=1
        )
        client.subscribe(
            f"$aws/provisioning-templates/{self.template_name}/provision/json/rejected", qos=1
        )

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.warning(f"Non-JSON message on {msg.topic}")
            return

        topic = msg.topic

        if topic == "$aws/certificates/create/json/accepted":
            self._cert_response = payload
            self._cert_event.set()
        elif topic == "$aws/certificates/create/json/rejected":
            self._error = payload.get("errorMessage", "unknown error")
            self._cert_event.set()
        elif topic.endswith("/provision/json/accepted"):
            self._provision_result = payload
            self._provision_event.set()
        elif topic.endswith("/provision/json/rejected"):
            self._error = payload.get("errorMessage", "unknown error")
            self._provision_event.set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _check_prerequisites():
    missing = []
    for path in [CLAIM_CERT, CLAIM_KEY, ROOT_CA]:
        if not path.exists():
            missing.append(str(path))
    if missing:
        logger.error("Missing claim certificate files:")
        for p in missing:
            logger.error(f"  {p}")
        logger.error("Run scripts/iot/bake_claim_cert.sh to fetch them.")
        sys.exit(1)


def _save_credentials(robot_id: str, cert_pem: str, private_key: str) -> None:
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    DEVICE_CERT.write_text(cert_pem)
    DEVICE_CERT.chmod(0o644)
    DEVICE_KEY.write_text(private_key)
    DEVICE_KEY.chmod(0o600)
    ROBOT_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROBOT_ID_FILE.write_text(robot_id)
    logger.info(f"Permanent cert  → {DEVICE_CERT}")
    logger.info(f"Private key     → {DEVICE_KEY}")
    logger.info(f"Robot ID        → {robot_id} ({ROBOT_ID_FILE})")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="RobotOps first-boot IoT provisioning")
    parser.add_argument(
        "--serial-number",
        required=True,
        help="Hardware serial number of this robot (e.g. CLEANBOT_0001)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-provision even if permanent cert already exists",
    )
    args = parser.parse_args()

    iot_endpoint = _require_env("IOT_ENDPOINT")
    template_name = os.environ.get("IOT_TEMPLATE_NAME", "robotops-dev-fleet-template")

    # Idempotency: skip if already provisioned
    if DEVICE_CERT.exists() and ROBOT_ID_FILE.exists() and not args.force:
        robot_id = ROBOT_ID_FILE.read_text().strip()
        logger.info(f"Already provisioned as {robot_id}. Use --force to re-provision.")
        sys.exit(0)

    _check_prerequisites()

    provisioner = FleetProvisioner(
        serial_number=args.serial_number,
        iot_endpoint=iot_endpoint,
        template_name=template_name,
    )
    credentials = provisioner.provision()
    _save_credentials(
        robot_id=credentials["robot_id"],
        cert_pem=credentials["cert_pem"],
        private_key=credentials["private_key"],
    )
    logger.info(f"Provisioning complete: {credentials['robot_id']}")


if __name__ == "__main__":
    main()
