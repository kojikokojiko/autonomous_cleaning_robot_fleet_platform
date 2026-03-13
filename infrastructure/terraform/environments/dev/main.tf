terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  backend "s3" {
    bucket         = "robotops-terraform-state"
    key            = "dev/terraform.tfstate"
    region         = "ap-northeast-1"
    encrypt        = true
    dynamodb_table = "robotops-terraform-lock"
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "robotops"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  env        = "dev"
  account_id = data.aws_caller_identity.current.account_id
  ecr_base   = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}

# ============================================================
# Networking
# ============================================================
module "networking" {
  source             = "../../global/networking"
  env                = local.env
  vpc_cidr           = "10.0.0.0/16"
  availability_zones = ["ap-northeast-1a", "ap-northeast-1c"]
}

# ============================================================
# IAM
# ============================================================
module "iam" {
  source = "../../global/iam"
  env    = local.env
}

# ============================================================
# S3
# ============================================================
module "s3" {
  source     = "../../modules/s3_storage"
  env        = local.env
  account_id = local.account_id
}

# ============================================================
# Kinesis (telemetry stream)
# ============================================================
module "kinesis" {
  source      = "../../modules/kinesis"
  env         = local.env
  shard_count = 2  # handles up to 100 robots at 1s interval
}

# ============================================================
# SQS DLQ
# ============================================================
module "telemetry_dlq" {
  source     = "../../modules/sqs_dlq"
  env        = local.env
  queue_name = "telemetry-processor"
}

module "ws_dlq" {
  source     = "../../modules/sqs_dlq"
  env        = local.env
  queue_name = "ws-connection-manager"
}

# ============================================================
# Lambda Functions
# ============================================================
module "lambda_telemetry_processor" {
  source          = "../../modules/lambda"
  env             = local.env
  function_name   = "telemetry-processor"
  description     = "Kinesis → TimescaleDB telemetry ingestion"
  lambda_role_arn = module.iam.lambda_execution_role_arn
  zip_path        = "${path.module}/../../../../lambda/telemetry-processor/function.zip"
  dlq_arn         = module.telemetry_dlq.queue_arn

  enable_kinesis_trigger = true
  kinesis_stream_arn     = module.kinesis.stream_arn
  kinesis_batch_size     = 100

  vpc_subnet_ids         = module.networking.private_subnet_ids
  vpc_security_group_ids = [module.networking.sg_lambda_id]

  environment_variables = {
    DB_SECRET_ARN = module.rds_operational.database_url_secret_arn
    ENV           = local.env
  }
}

module "lambda_ws_connect" {
  source          = "../../modules/lambda"
  env             = local.env
  function_name   = "ws-connect"
  description     = "WebSocket $connect handler"
  lambda_role_arn = module.iam.lambda_execution_role_arn
  zip_path        = "${path.module}/../../../../lambda/ws-connection-manager/function.zip"
  dlq_arn         = module.ws_dlq.queue_arn

  environment_variables = {
    REDIS_HOST = module.redis.primary_endpoint
    REDIS_PORT = tostring(module.redis.port)
    ENV        = local.env
  }
}

module "lambda_ws_disconnect" {
  source          = "../../modules/lambda"
  env             = local.env
  function_name   = "ws-disconnect"
  description     = "WebSocket $disconnect handler"
  lambda_role_arn = module.iam.lambda_execution_role_arn
  zip_path        = "${path.module}/../../../../lambda/ws-connection-manager/function.zip"
  dlq_arn         = module.ws_dlq.queue_arn

  environment_variables = {
    REDIS_HOST = module.redis.primary_endpoint
    REDIS_PORT = tostring(module.redis.port)
    ENV        = local.env
  }
}

module "lambda_ws_event_pusher" {
  source          = "../../modules/lambda"
  env             = local.env
  function_name   = "ws-event-pusher"
  description     = "EventBridge → WebSocket push"
  lambda_role_arn = module.iam.lambda_execution_role_arn
  zip_path        = "${path.module}/../../../../lambda/ws-event-pusher/function.zip"
  dlq_arn         = module.ws_dlq.queue_arn

  environment_variables = {
    REDIS_HOST      = module.redis.primary_endpoint
    REDIS_PORT      = tostring(module.redis.port)
    WS_API_ENDPOINT = module.api_gateway_websocket.endpoint
    ENV             = local.env
  }
}

module "lambda_iot_eventbridge_router" {
  source          = "../../modules/lambda"
  env             = local.env
  function_name   = "iot-eventbridge-router"
  description     = "IoT Core → EventBridge bridge"
  lambda_role_arn = module.iam.lambda_execution_role_arn
  zip_path        = "${path.module}/../../../../lambda/iot-event-bridge/function.zip"
  dlq_arn         = module.ws_dlq.queue_arn

  environment_variables = {
    EVENT_BUS_NAME = module.eventbridge.event_bus_name
    ENV            = local.env
  }
}

# ============================================================
# RDS (operational DB + timescaleDB)
# ============================================================
module "rds_operational" {
  source             = "../../modules/rds_postgres"
  env                = local.env
  db_name            = "robotops"
  private_subnet_ids = module.networking.private_subnet_ids
  sg_rds_id          = module.networking.sg_rds_id
  instance_class     = "db.t3.medium"
  allocated_storage  = 20
}

# ============================================================
# Redis
# ============================================================
module "redis" {
  source             = "../../modules/elasticache_redis"
  env                = local.env
  private_subnet_ids = module.networking.private_subnet_ids
  sg_redis_id        = module.networking.sg_redis_id
  node_type          = "cache.t3.micro"
}

# ============================================================
# ECS Cluster + Services
# ============================================================
module "ecs" {
  source                      = "../../modules/ecs_cluster"
  env                         = local.env
  region                      = var.region
  vpc_id                      = module.networking.vpc_id
  public_subnet_ids           = module.networking.public_subnet_ids
  private_subnet_ids          = module.networking.private_subnet_ids
  sg_alb_id                   = module.networking.sg_alb_id
  sg_ecs_id                   = module.networking.sg_ecs_id
  ecs_task_execution_role_arn = module.iam.ecs_task_execution_role_arn
  ecs_task_role_arn           = module.iam.ecs_task_role_arn

  services = {
    fleet-service = {
      image         = "${local.ecr_base}/robotops-fleet-service:latest"
      cpu           = 256
      memory        = 512
      desired_count = 1
      path_pattern  = "/api/v1/robots*"
      priority      = 10
      environment = {
        REDIS_URL = "redis://${module.redis.primary_endpoint}:${module.redis.port}"
        ENV       = local.env
      }
      secrets = {
        DATABASE_URL = module.rds_operational.database_url_secret_arn
      }
    }
    mission-service = {
      image         = "${local.ecr_base}/robotops-mission-service:latest"
      cpu           = 256
      memory        = 512
      desired_count = 1
      path_pattern  = "/api/v1/missions*"
      priority      = 20
      environment = {
        REDIS_URL         = "redis://${module.redis.primary_endpoint}:${module.redis.port}"
        FLEET_SERVICE_URL = "http://fleet-service:8000"
        ENV               = local.env
      }
      secrets = {
        DATABASE_URL = module.rds_operational.database_url_secret_arn
      }
    }
    telemetry-service = {
      image         = "${local.ecr_base}/robotops-telemetry-service:latest"
      cpu           = 256
      memory        = 512
      desired_count = 1
      path_pattern  = "/api/v1/telemetry*"
      priority      = 30
      environment = {
        ENV = local.env
      }
      secrets = {
        DATABASE_URL = module.rds_operational.database_url_secret_arn
      }
    }
    command-service = {
      image         = "${local.ecr_base}/robotops-command-service:latest"
      cpu           = 256
      memory        = 512
      desired_count = 1
      path_pattern  = "/api/v1/commands*"
      priority      = 50
      environment = {
        REDIS_URL       = "redis://${module.redis.primary_endpoint}:${module.redis.port}"
        WS_API_ENDPOINT = module.api_gateway_websocket.endpoint
        ENV             = local.env
      }
      secrets = {
        DATABASE_URL = module.rds_operational.database_url_secret_arn
      }
    }
    ota-service = {
      image         = "${local.ecr_base}/robotops-ota-service:latest"
      cpu           = 256
      memory        = 512
      desired_count = 1
      path_pattern  = "/api/v1/ota*"
      priority      = 60
      environment = {
        S3_BUCKET = module.s3.firmware_bucket_name
        ENV       = local.env
      }
      secrets = {
        DATABASE_URL = module.rds_operational.database_url_secret_arn
      }
    }
    digital-twin-service = {
      image         = "${local.ecr_base}/robotops-digital-twin-service:latest"
      cpu           = 256
      memory        = 512
      desired_count = 1
      path_pattern  = "/api/v1/twins*"
      priority      = 40
      environment = {
        ENV = local.env
      }
      secrets = {
        DATABASE_URL = module.rds_operational.database_url_secret_arn
      }
    }
  }
}

# ============================================================
# IoT Core
# ============================================================
module "iot_core" {
  source                            = "../../modules/iot_core"
  env                               = local.env
  region                            = var.region
  account_id                        = local.account_id
  kinesis_stream_name               = module.kinesis.stream_name
  iot_rule_role_arn                 = module.iam.iot_rule_role_arn
  iot_eventbridge_router_lambda_arn = module.lambda_iot_eventbridge_router.function_arn
}

# ============================================================
# WebSocket API Gateway
# ============================================================
module "api_gateway_websocket" {
  source                = "../../modules/api_gateway_websocket"
  env                   = local.env
  connect_lambda_arn    = module.lambda_ws_connect.function_arn
  disconnect_lambda_arn = module.lambda_ws_disconnect.function_arn
  default_lambda_arn    = module.lambda_ws_connect.function_arn
}

# ============================================================
# EventBridge
# ============================================================
module "eventbridge" {
  source               = "../../modules/eventbridge"
  env                  = local.env
  alert_lambda_arn     = module.lambda_ws_event_pusher.function_arn
  ws_pusher_lambda_arn = module.lambda_ws_event_pusher.function_arn
}

# ============================================================
# WAF
# ============================================================
module "waf" {
  source  = "../../modules/waf"
  env     = local.env
  alb_arn = module.ecs.alb_arn
}

# ============================================================
# REST API Gateway
# ============================================================
module "api_gateway_rest" {
  source             = "../../modules/api_gateway_rest"
  env                = local.env
  region             = var.region
  alb_listener_arn   = module.ecs.alb_listener_arn
  private_subnet_ids = module.networking.private_subnet_ids
  security_group_ids = [module.networking.sg_ecs_id]
  allowed_origins    = ["https://${module.cloudfront_dashboard.domain_name}"]
}

# ============================================================
# ECR Repositories
# ============================================================
locals {
  ecr_services = [
    "fleet-service",
    "mission-service",
    "telemetry-service",
    "command-service",
    "ota-service",
    "digital-twin-service",
  ]
}

resource "aws_ecr_repository" "services" {
  for_each = toset(local.ecr_services)

  name                 = "robotops-${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project     = "robotops"
    Environment = local.env
    ManagedBy   = "terraform"
  }
}

resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# ============================================================
# CloudFront + Dashboard S3 Bucket
# ============================================================
module "cloudfront_dashboard" {
  source     = "../../modules/cloudfront_dashboard"
  env        = local.env
  account_id = local.account_id
}

# ============================================================
# GitHub Actions OIDC — Keyless AWS Authentication
# ============================================================
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = {
    Project   = "robotops"
    ManagedBy = "terraform"
  }
}

resource "aws_iam_role" "github_actions" {
  name = "robotops-${local.env}-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # Allow all branches/tags in the repo
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*"
        }
      }
    }]
  })

  tags = {
    Project     = "robotops"
    Environment = local.env
    ManagedBy   = "terraform"
  }
}

# AdministratorAccess for dev: Terraform needs to create/destroy all resources.
# Scope down to specific actions in production.
resource "aws_iam_role_policy_attachment" "github_actions_admin" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
