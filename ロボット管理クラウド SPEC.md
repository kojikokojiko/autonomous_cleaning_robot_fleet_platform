# RobotOps Platform SPEC

## Autonomous Cleaning Robot Fleet Platform

Version: 3.1 Author: Koji Iwase

This document specifies a production-grade robotics cloud platform for
managing fleets of autonomous cleaning robots.
The system combines robotics, cloud infrastructure, IoT architecture,
and Infrastructure-as-Code.

------------------------------------------------------------------------

# 1. System Overview

The Autonomous Cleaning Robot Fleet Platform is a **RobotOps system**
designed to manage large fleets of robots operating in real-world
facilities.

Target facilities:

-   Office buildings
-   Airports
-   Hospitals
-   Shopping malls
-   Warehouses

Core capabilities:

-   Fleet Management
-   Mission Scheduling
-   Real-time Telemetry Streaming
-   Map Visualization
-   OTA Update
-   Event Driven Monitoring
-   Multi-Robot Task Allocation
-   Fleet Observability
-   Robot Fleet Deployment

------------------------------------------------------------------------

# 2. Design Philosophy

Robots are treated as managed infrastructure.

Concept:

Robot = Cloud Managed Device

Operational Model:

RobotOps = DevOps for Robots

Capabilities:

-   Fleet Observability
-   Fleet Control
-   Fleet Deployment
-   Fleet Analytics

------------------------------------------------------------------------

# 3. High-Level Architecture

```
Robots (ROS2)
    |
    | MQTT (QoS 1, mTLS)
    v
AWS IoT Core
    |
    +------------------+
    |                  |
    v                  v
EventBridge       Kinesis Stream
(Event Bus)       (Telemetry)
    |                  |
    v                  v
Subscriber        Lambda
Services          Processing
    |                  |
    v                  v
Alert / Analytics  Time-Series DB
                  (TimescaleDB)

Admin Dashboard (React)
    |
    +-------------------+
    |                   |
    v                   v
REST API           WebSocket API
(API Gateway)      (API Gateway)
    |                   |
    v                   v
Backend Services   Real-time Push
(ECS/Fargate)      (Telemetry, Events)
    |
    v
PostgreSQL / Redis / S3
```

------------------------------------------------------------------------

# 4. Robot Architecture

Robots run a ROS2 stack.

ROS2 Nodes:

-   sensors
-   slam_toolbox
-   nav2 navigation
-   cleaning_controller
-   robot_agent

robot_agent responsibilities:

-   publish telemetry (MQTT QoS 0, topic: robot/{id}/telemetry)
-   receive commands (MQTT QoS 1, topic: robot/{id}/command)
-   publish events (MQTT QoS 1, topic: robot/{id}/events)
-   perform OTA updates (MQTT QoS 1, topic: robot/{id}/ota)
-   maintain persistent MQTT session (clean_session = false)

Telemetry interval: 1--5 seconds.

------------------------------------------------------------------------

# 5. Communication Architecture

Protocol: MQTT

Broker: AWS IoT Core

Authentication: mTLS (X.509 certificates per robot)

Topic structure:

```
robot/{robot_id}/telemetry    # QoS 0 - high frequency, loss acceptable
robot/{robot_id}/events       # QoS 1 - guaranteed delivery
robot/{robot_id}/mission      # QoS 1 - guaranteed delivery
robot/{robot_id}/command      # QoS 1 - guaranteed delivery
robot/{robot_id}/command/ack  # QoS 1 - robot → cloud acknowledgment
robot/{robot_id}/ota          # QoS 1 - guaranteed delivery
```

MQTT Session: clean_session = false for command and event topics,
ensuring commands are delivered even after temporary disconnection.

------------------------------------------------------------------------

# 6. Event Driven Architecture

Robot generated events:

-   RobotBatteryLow
-   RobotStuck
-   CollisionDetected
-   MissionStarted
-   MissionCompleted

Pipeline:

Robot → MQTT → AWS IoT Core → EventBridge → Subscriber Services

Subscribers:

-   Alert Service
-   Analytics Service
-   Dashboard (via WebSocket push)

------------------------------------------------------------------------

# 7. Fleet Observability

Telemetry metrics include:

-   battery level
-   robot position
-   navigation status
-   motor load
-   sensor health
-   mission progress

Telemetry pipeline:

```
Robot → MQTT → IoT Core → Kinesis Data Stream → Lambda Processing → TimescaleDB
                                                        |
                                                        v
                                                   DLQ (SQS)
                                               (on processing failure)
```

Dashboards display:

-   fleet uptime
-   robot health
-   mission success rate

------------------------------------------------------------------------

# 8. Fleet Control

Operators can issue commands:

-   Start mission
-   Pause mission
-   Return to charging dock
-   Emergency stop

Command flow:

```
Dashboard → Command Service → IoT Core MQTT Publish (QoS 1)
                                      |
                                      v
                                   Robot
                                      |
                                      v (robot/{id}/command/ack)
                             Command Service ← ACK received
                                      |
                                   (if no ACK within timeout)
                                      v
                                  Retry / Alert
```

Safety requirements:

-   Emergency stop must use MQTT QoS 1 with ACK verification
-   Command timeout: 5 seconds, max 3 retries
-   Unacknowledged emergency stop triggers operator alert

------------------------------------------------------------------------

# 9. Mission Scheduling

Mission Service responsibilities:

-   mission creation
-   mission scheduling
-   mission assignment

Example mission:

Clean Zone A\
Start Time: 22:00\
Priority: High

------------------------------------------------------------------------

# 10. Multi-Robot Task Allocation

MVP algorithm:

Nearest Robot First

Scoring factors:

-   normalized distance (0.0 - 1.0)
-   normalized battery level (0.0 - 1.0)
-   robot availability (boolean)

Score formula (lower is better):

```
distance_score  = distance_to_zone / max_distance     # normalized [0,1]
battery_score   = (100 - battery_level) / 100         # normalized [0,1]
score = w1 * distance_score + w2 * battery_score
        (default: w1=0.6, w2=0.4)
```

Only robots with battery_level > 20% and status = available are candidates.

Future algorithms:

-   Hungarian algorithm
-   Auction-based allocation
-   Reinforcement learning

------------------------------------------------------------------------

# 11. Map System

Map format:

ROS Occupancy Grid

Storage:

Amazon S3

Dashboard features:

-   robot position (real-time via WebSocket)
-   cleaning path overlay
-   zone visualization

Rendering:

Three.js / WebGL

------------------------------------------------------------------------

# 13. OTA Update System

OTA flow:

1.  firmware uploaded to S3
2.  OTA service creates update job
3.  robots notified via MQTT (robot/{id}/ota)
4.  robot verifies checksum before applying
5.  robot downloads update from S3 (pre-signed URL)
6.  robot restarts software container (only when docked / idle)

Safety conditions:

-   OTA update only applied when robot status = docked or idle
-   Mid-mission robots queue the update for next dock cycle

Deployment strategy:

Rolling updates (default)\
Canary deployment (optional, configurable percentage)

Rollback:

-   Previous firmware version retained in S3
-   Automatic rollback on boot failure (3 consecutive restart failures)

------------------------------------------------------------------------

# 14. Data Storage

Operational database:

PostgreSQL (Amazon RDS)

Tables: robots, missions, events, firmware, maps

Time-series database:

TimescaleDB extension on a dedicated RDS instance

Tables: telemetry (hypertable, partitioned by time)

Cache:

Amazon ElastiCache (Redis)

Uses:
-   session data
-   command deduplication
-   WebSocket pub/sub

------------------------------------------------------------------------

# 15. Security Architecture

## Authentication

-   Operators: Amazon Cognito User Pool + JWT tokens
-   API Gateway: Cognito Authorizer
-   Robots: mTLS via X.509 certificates (provisioned per robot)

## Secret Management

-   AWS Secrets Manager: database credentials, API keys
-   AWS Systems Manager Parameter Store: runtime configuration

## Network Isolation

-   VPC with private subnets for ECS services and RDS
-   Public subnets for API Gateway and Load Balancer only
-   Security Groups: least-privilege ingress/egress rules

## API Protection

-   AWS WAF on API Gateway (rate limiting, IP filtering)
-   HTTPS enforced on all endpoints

## Role-Based Access Control

-   Admin: full fleet control, OTA deployment, user management
-   Operator: mission control, robot commands
-   Viewer: read-only telemetry and dashboards

------------------------------------------------------------------------

# 16. Real-time Communication

Real-time data delivery to the dashboard uses API Gateway WebSocket API.

WebSocket flow:

```
Dashboard (React)
    |
    | WebSocket connect (with Cognito JWT)
    v
API Gateway WebSocket API
    |
    v
Connection Manager (Lambda)
    |
    v (stores connectionId)
ElastiCache (Redis)

Push sources:
- Telemetry Lambda → Redis pub/sub → Connection Manager → WebSocket push
- EventBridge (events) → Lambda → WebSocket push
```

Push event types:

-   `telemetry_update`: robot position and sensor data
-   `robot_event`: RobotStuck, BatteryLow, etc.
-   `mission_update`: mission status changes

------------------------------------------------------------------------

# 17. AWS Infrastructure

Core AWS services:

-   AWS IoT Core
-   Amazon EventBridge
-   Amazon Kinesis Data Streams
-   AWS Lambda
-   Amazon SQS (Dead Letter Queue)
-   Amazon API Gateway (REST + WebSocket)
-   Amazon ECS / Fargate
-   Amazon RDS (PostgreSQL + TimescaleDB)
-   Amazon ElastiCache (Redis)
-   Amazon S3
-   Amazon CloudWatch
-   Amazon Cognito
-   AWS Secrets Manager
-   AWS Systems Manager Parameter Store
-   AWS WAF
-   Amazon DynamoDB (Terraform state locking)

------------------------------------------------------------------------

# 18. Infrastructure as Code (Terraform)

All infrastructure is managed using Terraform.

Goals:

-   reproducible infrastructure
-   version controlled infrastructure
-   environment isolation
-   automated deployment

------------------------------------------------------------------------

# 19. Terraform Repository Structure

```
robotops-platform/
├── robot-agent/
├── backend-services/
├── dashboard/
├── simulation/
├── docs/
└── infrastructure/
    └── terraform/
        ├── modules/
        │   ├── iot_core
        │   ├── eventbridge
        │   ├── kinesis
        │   ├── lambda
        │   ├── sqs_dlq
        │   ├── ecs_cluster
        │   ├── rds_postgres
        │   ├── elasticache_redis
        │   ├── s3_storage
        │   ├── api_gateway_rest
        │   ├── api_gateway_websocket
        │   ├── cognito
        │   └── waf
        ├── environments/
        │   ├── dev
        │   ├── staging
        │   └── prod
        └── global/
            ├── iam
            └── networking
```

------------------------------------------------------------------------

# 20. Terraform Modules

Core modules:

| Module | Provisions |
|---|---|
| iot_core | IoT Thing, Policy, Certificate, Topic Rules |
| eventbridge | Event Bus, Rules, Targets |
| kinesis_stream | Kinesis Data Stream, shards |
| lambda | Lambda function, IAM role, CloudWatch log group |
| sqs_dlq | Dead Letter Queue for Lambda failures |
| ecs_cluster | ECS Cluster, Service, Task Definition, ALB |
| rds_postgres | RDS instance, subnet group, security group |
| elasticache_redis | Redis cluster, subnet group |
| s3_storage | S3 buckets (maps, firmware, terraform state) |
| api_gateway_rest | REST API, stages, Cognito authorizer |
| api_gateway_websocket | WebSocket API, routes, Lambda integrations |
| cognito | User Pool, App Client, identity providers |
| waf | WAF Web ACL, rules, rate limiting |

------------------------------------------------------------------------

# 21. Telemetry Infrastructure (Terraform)

Telemetry pipeline infrastructure:

```
IoT Core → Kinesis Data Stream → Lambda processing → TimescaleDB
                                        |
                                        v (on failure)
                                    SQS DLQ → CloudWatch Alert
```

Terraform resources include:

-   aws_kinesis_stream (shard count: scale with robot fleet size)
-   aws_lambda_function (telemetry processor)
-   aws_lambda_event_source_mapping (Kinesis → Lambda)
-   aws_sqs_queue (dead letter queue)
-   aws_cloudwatch_log_group
-   aws_iam_role

Kinesis shard sizing: 1 shard per 50 robots at 1s telemetry interval.

------------------------------------------------------------------------

# 22. Backend Infrastructure

Backend services run on ECS Fargate.

Services:

-   fleet-service: robot registry, status management
-   mission-service: mission CRUD, scheduling, task allocation
-   telemetry-service: telemetry query API
-   ota-service: firmware management, update job coordination
-   command-service: command dispatch, ACK tracking, WebSocket push

Terraform resources:

-   aws_ecs_cluster
-   aws_ecs_service (one per microservice)
-   aws_ecs_task_definition
-   aws_lb
-   aws_lb_listener

------------------------------------------------------------------------

# 23. Database Infrastructure

Operational database module provisions:

-   aws_db_instance (PostgreSQL, private subnet)
-   aws_db_subnet_group
-   aws_security_group (ECS services only)

Time-series database module provisions:

-   aws_db_instance (PostgreSQL + TimescaleDB extension, private subnet)
-   aws_db_subnet_group
-   aws_security_group

Engine: PostgreSQL 15\
Extension: TimescaleDB (telemetry hypertable)

------------------------------------------------------------------------

# 24. Terraform State Management

State storage:

S3 backend

```hcl
terraform {
  backend "s3" {
    bucket         = "robotops-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "ap-northeast-1"
    encrypt        = true
    dynamodb_table = "robotops-terraform-lock"
  }
}
```

State locking: DynamoDB

------------------------------------------------------------------------

# 25. CI/CD Integration

Infrastructure deployment pipeline:

```
commit → terraform fmt → terraform validate → terraform plan → (manual approval) → terraform apply
```

Application deployment pipeline:

```
commit → unit tests → build Docker image → push to ECR → ECS rolling deploy
```

CI/CD platform: GitHub Actions

------------------------------------------------------------------------

# 26. Simulation Environment

Simulation tools:

-   Gazebo
-   NVIDIA Isaac Sim

Simulation capabilities:

-   multi-robot simulation
-   navigation testing
-   mission scheduling validation

Target scale: 100 simulated robots.

------------------------------------------------------------------------

# 27. MVP Scope

Initial implementation includes:

-   fleet management (fleet-service)
-   telemetry ingestion (Kinesis → Lambda → TimescaleDB)
-   mission scheduling (mission-service)
-   map visualization (S3 + Three.js + WebSocket position overlay)
-   OTA updates (ota-service)
-   event monitoring (EventBridge → alert-service)
-   real-time dashboard (WebSocket API)
-   authentication (Cognito)

------------------------------------------------------------------------

# 28. Portfolio Value

This project demonstrates expertise in:

-   robotics systems (ROS2, SLAM, Nav2)
-   cloud architecture (AWS, event-driven, microservices)
-   IoT platforms (MQTT, AWS IoT Core)
-   distributed systems (ECS, async messaging)
-   real-time data pipelines (Kinesis, TimescaleDB)
-   infrastructure as code (Terraform, modular design)
-   security architecture (Cognito, mTLS, VPC, WAF)

The architecture reflects production-grade robot fleet platforms.
