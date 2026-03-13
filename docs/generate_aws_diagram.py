"""
Generate AWS architecture diagram for the RobotOps platform.
Output: docs/aws_architecture.png
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.iot import IotCore
from diagrams.aws.analytics import KinesisDataStreams
from diagrams.aws.compute import Lambda, ECS
from diagrams.aws.database import RDS, ElastiCache
from diagrams.aws.network import ALB, APIGateway
from diagrams.aws.security import WAF
from diagrams.aws.storage import S3
from diagrams.aws.integration import Eventbridge, SQS
from diagrams.onprem.client import Client
from diagrams.onprem.compute import Server
from diagrams.aws.devtools import Codecommit
import os

output_path = os.path.join(os.path.dirname(__file__), "aws_architecture")

graph_attr = {
    "fontsize":  "12",
    "bgcolor":   "white",
    "fontcolor": "#1f2328",
    "pad":       "1.2",
    "splines":   "ortho",
    "nodesep":   "0.8",
    "ranksep":   "1.2",
    "rankdir":   "TB",
}

with Diagram(
    "RobotOps Platform — AWS Architecture (ap-northeast-1)",
    filename=output_path,
    show=False,
    direction="TB",
    graph_attr=graph_attr,
    outformat="png",
):
    # Row 0 — Dashboard (top)
    dashboard = Client("Dashboard\nReact + Three.js")

    # Row 1 — API Layer
    with Cluster("API Layer"):
        waf     = WAF("WAF")
        rest_gw = APIGateway("REST API GW")
        ws_gw   = APIGateway("WebSocket\nAPI GW")
        lconn   = Lambda("Lambda\nws-connection-mgr")

    # Row 2 — Core (IoT + VPC)
    iot = IotCore("AWS IoT Core\nMQTT Broker")

    with Cluster("VPC  10.0.0.0/16"):
        alb = ALB("ALB")

        with Cluster("ECS Fargate  [private subnet]"):
            svcs = [
                ECS("fleet-service"),
                ECS("mission-service"),
                ECS("command-service"),
                ECS("telemetry-service"),
                ECS("ota-service"),
                ECS("digital-twin-service"),
            ]
            fleet_svc, miss_svc, cmd_svc, telem_svc, ota_svc, twin_svc = svcs

        with Cluster("Storage  [private subnet]"):
            rds   = RDS("RDS PostgreSQL\n+ TimescaleDB")
            redis = ElastiCache("ElastiCache Redis")

        s3 = S3("S3 Firmware")

    # Row 3 — Data Pipelines
    with Cluster("Telemetry Pipeline"):
        kinesis = KinesisDataStreams("Kinesis\n2 shards")
        ltel    = Lambda("Lambda\ntelemetry-processor")
        dlq1    = SQS("SQS DLQ")

    with Cluster("Event Pipeline"):
        liot_router = Lambda("Lambda\niot-event-bridge")
        evb   = Eventbridge("EventBridge")
        levt  = Lambda("Lambda\nws-event-pusher")
        dlq2  = SQS("SQS DLQ")

    # Row 4 — Robots
    with Cluster("Robot Fleet  (Edge)"):
        robots = Server("robot_001 … N\nPython Agent / mTLS X.509")

    # CI/CD
    with Cluster("CI/CD"):
        github = Codecommit("GitHub Actions")
        ecr    = S3("ECR")

    # ══ Edges ═════════════════════════════════════════════════

    # Dashboard ↔ API
    dashboard >> Edge(label="HTTPS") >> waf
    dashboard >> Edge(label="WebSocket", color="#ce93d8") >> ws_gw
    ws_gw >> Edge(label="server push", color="#ce93d8", style="dashed") >> dashboard

    # API layer internal — WAF attaches to ALB
    waf >> alb
    rest_gw >> alb

    # WebSocket mgr
    redis >> Edge(label="SUBSCRIBE", color="#ce93d8") >> lconn
    lconn >> ws_gw

    # ALB → ECS
    alb >> [fleet_svc, miss_svc, cmd_svc, telem_svc, ota_svc, twin_svc]

    # ECS → Storage
    [fleet_svc, miss_svc, cmd_svc, telem_svc, ota_svc, twin_svc] >> rds
    [fleet_svc, cmd_svc] >> redis
    ota_svc >> s3

    # command-service → IoT Core
    cmd_svc >> Edge(label="MQTT publish", color="#ffb74d") >> iot

    # IoT Core → Pipelines
    iot >> Edge(label="IoT Rule", color="#4fc3f7") >> kinesis
    iot >> Edge(label="IoT Rule", color="#81c784") >> liot_router
    liot_router >> Edge(color="#81c784") >> evb

    # Telemetry pipeline
    kinesis >> ltel
    ltel >> Edge(label="batch upsert\n+ robots table", color="#4fc3f7") >> rds
    ltel >> Edge(color="#ef5350", style="dashed") >> dlq1

    # Event pipeline
    evb >> levt
    levt >> Edge(label="PUBLISH", color="#ce93d8") >> redis
    levt >> Edge(label="Mgmt API push", color="#ce93d8") >> ws_gw  # direct push to connected clients
    levt >> Edge(color="#ef5350", style="dashed") >> dlq2

    # Robots ↔ IoT Core
    robots >> Edge(label="QoS 0  telemetry", color="#4fc3f7") >> iot
    robots >> Edge(label="QoS 1  events",    color="#81c784") >> iot
    iot >> Edge(label="QoS 1  commands/OTA", color="#ffb74d", style="dashed") >> robots

    # Robot OTA download
    robots >> Edge(label="HTTP firmware DL", color="#ffb74d", style="dashed") >> rest_gw

    # CI/CD
    github >> ecr >> Edge(label="deploy") >> alb

print(f"Saved: {output_path}.png")
