"""
Telemetry flow diagram: Robot → IoT Core → Kinesis/EventBridge → Lambda → Dashboard
Output: docs/flow_telemetry.png
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.iot import IotCore
from diagrams.aws.analytics import KinesisDataStreams
from diagrams.aws.compute import Lambda
from diagrams.aws.database import RDS
from diagrams.aws.network import APIGateway
from diagrams.aws.integration import Eventbridge, SQS
from diagrams.aws.database import ElastiCache
from diagrams.onprem.client import Client
from diagrams.onprem.compute import Server
import os

output_path = os.path.join(os.path.dirname(__file__), "flow_telemetry")

graph_attr = {
    "fontsize":  "13",
    "bgcolor":   "white",
    "fontcolor": "#1f2328",
    "pad":       "1.0",
    "splines":   "ortho",
    "nodesep":   "0.9",
    "ranksep":   "1.4",
    "rankdir":   "TB",
    "label":     "テレメトリフロー  —  Robot → Browser",
    "labelloc":  "t",
    "labeljust": "c",
}

with Diagram(
    "テレメトリフロー",
    filename=output_path,
    show=False,
    direction="TB",
    graph_attr=graph_attr,
    outformat="png",
):
    robot = Server("robot_001 … N\nMQTT QoS 0\n毎秒 telemetry")

    iot = IotCore("AWS IoT Core\nMQTT Broker")

    with Cluster("Telemetry Pipeline  (DB 書き込み)"):
        kinesis = KinesisDataStreams("Kinesis\n2 shards")
        ltel    = Lambda("Lambda\ntelemetry-processor")
        dlq     = SQS("SQS DLQ")
        rds     = RDS("RDS PostgreSQL\n+ TimescaleDB")

    with Cluster("Event Pipeline  (リアルタイム Push)"):
        evb   = Eventbridge("EventBridge")
        redis = ElastiCache("ElastiCache Redis\nws:connections")
        levt  = Lambda("Lambda\nws-event-pusher")

    ws_gw     = APIGateway("WebSocket\nAPI GW")
    dashboard = Client("Dashboard\nReact + Three.js")

    # Robot → IoT Core
    robot >> Edge(label="MQTT QoS 0\nrobot/{id}/telemetry", color="#4fc3f7") >> iot

    # IoT Core → 2 rules
    iot >> Edge(label="IoT Rule 1", color="#4fc3f7") >> kinesis
    iot >> Edge(label="IoT Rule 2", color="#81c784") >> evb

    # Telemetry pipeline
    kinesis >> Edge(color="#4fc3f7") >> ltel
    ltel >> Edge(label="UPSERT robots\nINSERT telemetry", color="#4fc3f7") >> rds
    ltel >> Edge(label="失敗時", color="#ef5350", style="dashed") >> dlq

    # Event pipeline
    evb >> Edge(color="#81c784") >> levt
    levt >> Edge(label="SMEMBERS\nws:connections", color="#ce93d8", style="dashed") >> redis
    levt >> Edge(label="post_to_connection\ntelemetry_update", color="#ce93d8") >> ws_gw

    # WebSocket → Dashboard
    ws_gw >> Edge(label="WebSocket push", color="#ce93d8") >> dashboard

print(f"✅  Saved: {output_path}.png")
