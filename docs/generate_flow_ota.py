"""
OTA flow diagram: Dashboard → ota-service → MQTT → Robot → S3 → Events → Browser
Output: docs/flow_ota.png
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.iot import IotCore
from diagrams.aws.compute import Lambda, ECS
from diagrams.aws.database import RDS
from diagrams.aws.network import APIGateway, ALB
from diagrams.aws.security import WAF, Cognito
from diagrams.aws.storage import S3
from diagrams.aws.integration import Eventbridge
from diagrams.aws.database import ElastiCache
from diagrams.onprem.client import Client
from diagrams.onprem.compute import Server
import os

output_path = os.path.join(os.path.dirname(__file__), "flow_ota")

graph_attr = {
    "fontsize":  "13",
    "bgcolor":   "white",
    "fontcolor": "#1f2328",
    "pad":       "1.0",
    "splines":   "ortho",
    "nodesep":   "0.9",
    "ranksep":   "1.4",
    "rankdir":   "TB",
    "label":     "OTA デプロイフロー  —  Dashboard → Robot",
    "labelloc":  "t",
    "labeljust": "c",
}

with Diagram(
    "OTA デプロイフロー",
    filename=output_path,
    show=False,
    direction="TB",
    graph_attr=graph_attr,
    outformat="png",
):
    dashboard = Client("Dashboard\nReact")

    with Cluster("API / Auth Layer"):
        waf     = WAF("WAF")
        rest_gw = APIGateway("REST API GW\n+ Cognito JWT")
        cognito = Cognito("Cognito")
        alb     = ALB("ALB")

    waf - cognito

    with Cluster("ECS Fargate"):
        ota_svc   = ECS("ota-service")
        fleet_svc = ECS("fleet-service")

    rds = RDS("RDS PostgreSQL")
    s3  = S3("S3 Firmware")
    iot = IotCore("AWS IoT Core")

    robot = Server("Robot\n(idle / docked)")

    with Cluster("イベント → ブラウザ Push"):
        evb   = Eventbridge("EventBridge")
        levt  = Lambda("Lambda\nws-event-pusher")
        redis = ElastiCache("Redis\nws:connections")
        ws_gw = APIGateway("WebSocket\nAPI GW")

    # ① Dashboard → API
    dashboard >> Edge(label="① POST /ota/jobs\nHTTPS", color="#ffb74d") >> waf
    waf >> rest_gw >> alb >> ota_svc

    # ② ota-service: DB 保存 + MQTT
    ota_svc >> Edge(label="② job 保存", color="#ffb74d", style="dashed") >> rds
    ota_svc >> Edge(label="③ MQTT QoS 1\nrobot/{id}/ota", color="#ffb74d") >> iot

    # ③ IoT Core → Robot
    iot >> Edge(label="④ OTA コマンド\n(persistent session)", color="#ffb74d") >> robot

    # ④ Robot: firmware download
    robot >> Edge(label="⑤ HTTP GET\nfirmware download", color="#4fc3f7", style="dashed") >> rest_gw
    rest_gw >> alb >> ota_svc
    ota_svc >> Edge(label="⑥ firmware bytes\n+ checksum", color="#4fc3f7", style="dashed") >> s3

    # ⑤ Robot → events
    robot >> Edge(label="⑦ MQTT QoS 1\nOTADownloading/Applying\nOTACompleted/Failed", color="#81c784") >> iot

    # ⑥ events → fleet-service → ota-service
    iot >> Edge(label="⑧ events", color="#81c784") >> fleet_svc
    fleet_svc >> Edge(label="⑨ PATCH job status", color="#81c784", style="dashed") >> ota_svc

    # ⑦ events → browser
    iot >> Edge(label="⑩ IoT Rule", color="#81c784") >> evb
    evb >> levt
    levt >> Edge(style="dashed") >> redis
    levt >> Edge(label="⑪ OTA 進捗 push", color="#ce93d8") >> ws_gw
    ws_gw >> Edge(label="WebSocket", color="#ce93d8") >> dashboard

print(f"✅  Saved: {output_path}.png")
