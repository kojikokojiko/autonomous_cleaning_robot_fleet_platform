"""
Fleet Simulator - runs N robots locally without ROS2.

Usage:
  python -m simulation.fleet_simulator --robots 5 --broker localhost --port 1883

Each robot runs in its own thread with staggered start positions and battery levels.
"""
import argparse
import logging
import random
import signal
import sys
from threading import Thread
import time

from src.nodes.robot_agent import RobotAgent
from src.nodes.state import RobotState, RobotStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("fleet_simulator")


def create_robot(
    robot_index: int,
    broker: str,
    port: int,
    telemetry_interval: float,
    tls_cert: str = None,
    tls_key: str = None,
    tls_ca: str = None,
) -> RobotAgent:
    robot_id = f"robot_{robot_index:03d}"
    initial_state = RobotState(
        robot_id=robot_id,
        status=RobotStatus.IDLE,
        battery_level=random.uniform(40.0, 100.0),
        position_x=random.uniform(0.0, 20.0),
        position_y=random.uniform(0.0, 15.0),
        floor=1,
    )
    return RobotAgent(
        robot_id=robot_id,
        mqtt_broker=broker,
        mqtt_port=port,
        telemetry_interval=telemetry_interval,
        initial_state=initial_state,
        tls_cert=tls_cert,
        tls_key=tls_key,
        tls_ca=tls_ca,
    )


def main():
    parser = argparse.ArgumentParser(description="RobotOps Fleet Simulator")
    parser.add_argument("--robots",   type=int,   default=5,    help="Number of robots to simulate")  # noqa: E501
    parser.add_argument("--broker",   type=str,   default="localhost", help="MQTT broker host")
    parser.add_argument("--port",     type=int,   default=1883, help="MQTT broker port")
    parser.add_argument("--interval", type=float, default=0.5,  help="Telemetry interval (seconds)")  # noqa: E501
    parser.add_argument("--cert",     type=str,   default=None, help="TLS certificate file (for AWS IoT Core)")
    parser.add_argument("--key",      type=str,   default=None, help="TLS private key file (for AWS IoT Core)")
    parser.add_argument("--ca",       type=str,   default=None, help="CA certificate file (for AWS IoT Core)")
    args = parser.parse_args()

    logger.info(f"Starting fleet simulator: {args.robots} robots → {args.broker}:{args.port}")

    agents: list[RobotAgent] = []
    threads: list[Thread] = []

    for i in range(1, args.robots + 1):
        agent = create_robot(i, args.broker, args.port, args.interval,
                             tls_cert=args.cert, tls_key=args.key, tls_ca=args.ca)
        agents.append(agent)

        t = Thread(target=agent.start, daemon=True, name=f"robot_{i:03d}")
        threads.append(t)
        t.start()
        time.sleep(0.2)  # stagger connection

    logger.info(f"All {len(agents)} robots running. Press Ctrl+C to stop.")

    def shutdown(sig, frame):
        logger.info("Shutting down fleet simulator...")
        for agent in agents:
            agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
