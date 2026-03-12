# RobotOps Platform

**Autonomous Cleaning Robot Fleet Platform**

A production-grade RobotOps system for managing fleets of autonomous cleaning robots.

## Architecture

```
Robots (ROS2) → MQTT → AWS IoT Core → EventBridge / Kinesis → Backend Services → Dashboard
```

See [SPEC](./ロボット管理クラウド%20SPEC.md) for full architecture details.

## Repository Structure

```
robotops-platform/
├── robot-agent/          # ROS2-compatible robot agent (Python)
├── backend-services/     # Microservices (FastAPI / Python)
│   ├── fleet-service/
│   ├── mission-service/
│   ├── telemetry-service/
│   ├── command-service/
│   ├── ota-service/
│   └── shared/
├── lambda/               # AWS Lambda functions
│   ├── telemetry-processor/
│   ├── ws-connection-manager/
│   └── ws-event-pusher/
├── dashboard/            # React + TypeScript frontend
├── infrastructure/       # Terraform IaC
│   └── terraform/
│       ├── modules/
│       ├── environments/
│       └── global/
├── simulation/           # Gazebo / multi-robot simulation
└── docs/
```

## Tech Stack

| Layer | Technology |
|---|---|
| Robot | ROS2 (Humble), Python, MQTT (paho-mqtt) |
| IoT Broker | AWS IoT Core |
| Event Bus | Amazon EventBridge |
| Telemetry Pipeline | Amazon Kinesis + AWS Lambda |
| Backend Services | FastAPI (Python 3.11), ECS Fargate |
| Database | PostgreSQL + TimescaleDB (RDS) |
| Cache | Redis (ElastiCache) |
| Real-time | API Gateway WebSocket API |
| Auth | WAF (レート制限・不正リクエスト防御) |
| Storage | Amazon S3 |
| IaC | Terraform |
| CI/CD | GitHub Actions |
| Dashboard | React + TypeScript + Three.js |

## Quick Start (Local Development)

```bash
# Start all services locally
docker compose up -d

# Run robot simulator
cd robot-agent && python -m simulation.fleet_simulator --robots 5

# Access dashboard
open http://localhost:3000
```

## Infrastructure Deployment

```bash
cd infrastructure/terraform/environments/dev
terraform init
terraform plan
terraform apply
```
