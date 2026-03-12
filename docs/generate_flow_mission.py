"""
Mission flow diagram: Dashboard → mission-service → command-service → Robot → completion
Output: docs/flow_mission.png
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.iot import IotCore
from diagrams.aws.compute import Lambda, ECS
from diagrams.aws.database import RDS
from diagrams.aws.network import APIGateway, ALB
from diagrams.aws.security import WAF, Cognito
from diagrams.aws.integration import Eventbridge
from diagrams.aws.database import ElastiCache
from diagrams.onprem.client import Client
from diagrams.onprem.compute import Server
import os

output_path = os.path.join(os.path.dirname(__file__), "flow_mission")

graph_attr = {
    "fontsize":  "13",
    "bgcolor":   "white",
    "fontcolor": "#1f2328",
    "pad":       "1.0",
    "splines":   "ortho",
    "nodesep":   "0.9",
    "ranksep":   "1.4",
    "rankdir":   "TB",
    "label":     "ミッション送信フロー  —  Dashboard → Robot → 完了通知",
    "labelloc":  "t",
    "labeljust": "c",
}

with Diagram(
    "ミッション送信フロー",
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
        miss_svc  = ECS("mission-service")
        fleet_svc = ECS("fleet-service")
        cmd_svc   = ECS("command-service")

    rds = RDS("RDS PostgreSQL")
    iot = IotCore("AWS IoT Core")

    robot = Server("Robot\n(idle)")

    with Cluster("完了通知 → ブラウザ Push"):
        evb   = Eventbridge("EventBridge")
        levt  = Lambda("Lambda\nws-event-pusher")
        redis = ElastiCache("Redis\nws:connections")
        ws_gw = APIGateway("WebSocket\nAPI GW")

    # ① Dashboard → mission-service
    dashboard >> Edge(label="① POST /missions\n(zone, priority)", color="#81c784") >> waf
    waf >> rest_gw >> alb >> miss_svc

    # ② mission-service: save + get idle robots
    miss_svc >> Edge(label="② mission 保存\n(status: pending)", color="#81c784", style="dashed") >> rds
    miss_svc >> Edge(label="③ GET /robots?status=idle\nアイドルロボット取得", color="#4fc3f7", style="dashed") >> fleet_svc

    # ③ mission-service: allocate + command
    miss_svc >> Edge(label="④ スコア計算\n0.6×距離 + 0.4×バッテリー\n→ 最適ロボット選択", color="#81c784", style="dashed") >> rds
    miss_svc >> Edge(label="⑤ POST /commands\nstart_mission", color="#ffb74d") >> cmd_svc

    # ④ command-service → IoT Core → Robot
    cmd_svc >> Edge(label="⑥ MQTT QoS 1\nrobot/{id}/command\nstart_mission", color="#ffb74d") >> iot
    iot >> Edge(label="⑦ コマンド配送", color="#ffb74d") >> robot

    # ⑤ Robot: execute mission
    robot >> Edge(label="⑧ MQTT QoS 0\ntelemetry\n(mission_progress 0→100%)", color="#4fc3f7", style="dashed") >> iot
    robot >> Edge(label="⑨ MQTT QoS 1\nMissionCompleted event", color="#81c784") >> iot

    # ⑥ events → fleet-service → mission-service
    iot >> Edge(label="⑩ events", color="#81c784") >> fleet_svc
    fleet_svc >> Edge(label="⑪ PATCH mission\nstatus: completed", color="#81c784", style="dashed") >> miss_svc

    # ⑦ real-time push to dashboard
    iot >> Edge(label="⑫ IoT Rule", color="#81c784") >> evb
    evb >> levt
    levt >> Edge(style="dashed") >> redis
    levt >> Edge(label="⑬ mission_update push", color="#ce93d8") >> ws_gw
    ws_gw >> Edge(label="WebSocket", color="#ce93d8") >> dashboard

print(f"✅  Saved: {output_path}.png")
