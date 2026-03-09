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
  zip_path        = "${path.module}/../../../lambda/telemetry-processor/function.zip"
  dlq_arn         = module.telemetry_dlq.queue_arn

  kinesis_stream_arn  = module.kinesis.stream_arn
  kinesis_batch_size  = 100

  vpc_subnet_ids         = module.networking.private_subnet_ids
  vpc_security_group_ids = [module.networking.sg_lambda_id]

  environment_variables = {
    DATABASE_URL = "postgresql://robotops:placeholder@${module.rds_operational.endpoint}/robotops"
    ENV          = local.env
  }
}

module "lambda_ws_connect" {
  source          = "../../modules/lambda"
  env             = local.env
  function_name   = "ws-connect"
  description     = "WebSocket $connect handler"
  lambda_role_arn = module.iam.lambda_execution_role_arn
  zip_path        = "${path.module}/../../../lambda/ws-connection-manager/function.zip"
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
  zip_path        = "${path.module}/../../../lambda/ws-connection-manager/function.zip"
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
  zip_path        = "${path.module}/../../../lambda/ws-event-pusher/function.zip"
  dlq_arn         = module.ws_dlq.queue_arn

  environment_variables = {
    REDIS_HOST           = module.redis.primary_endpoint
    REDIS_PORT           = tostring(module.redis.port)
    WS_API_ENDPOINT      = module.api_gateway_websocket.endpoint
    ENV                  = local.env
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
# Cognito
# ============================================================
module "cognito" {
  source        = "../../modules/cognito"
  env           = local.env
  callback_urls = ["http://localhost:3000/callback"]
  logout_urls   = ["http://localhost:3000/logout"]
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
        DATABASE_URL = "postgresql://robotops:placeholder@${module.rds_operational.endpoint}/robotops"
        REDIS_URL    = "redis://${module.redis.primary_endpoint}:${module.redis.port}"
        ENV          = local.env
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
        DATABASE_URL      = "postgresql://robotops:placeholder@${module.rds_operational.endpoint}/robotops"
        REDIS_URL         = "redis://${module.redis.primary_endpoint}:${module.redis.port}"
        FLEET_SERVICE_URL = "http://fleet-service:8000"
        ENV               = local.env
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
        DATABASE_URL = "postgresql://robotops:placeholder@${module.rds_operational.endpoint}/robotops"
        ENV          = local.env
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
        DATABASE_URL = "postgresql://robotops:placeholder@${module.rds_operational.endpoint}/robotops"
        REDIS_URL    = "redis://${module.redis.primary_endpoint}:${module.redis.port}"
        ENV          = local.env
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
        DATABASE_URL    = "postgresql://robotops:placeholder@${module.rds_operational.endpoint}/robotops"
        REDIS_URL       = "redis://${module.redis.primary_endpoint}:${module.redis.port}"
        WS_API_ENDPOINT = module.api_gateway_websocket.endpoint
        ENV             = local.env
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
        DATABASE_URL    = "postgresql://robotops:placeholder@${module.rds_operational.endpoint}/robotops"
        S3_BUCKET       = module.s3.firmware_bucket_name
        ENV             = local.env
      }
    }
  }
}

# ============================================================
# IoT Core
# ============================================================
module "iot_core" {
  source              = "../../modules/iot_core"
  env                 = local.env
  region              = var.region
  account_id          = local.account_id
  kinesis_stream_name = module.kinesis.stream_name
  iot_rule_role_arn   = module.iam.iot_rule_role_arn
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
  auth_lambda_arn       = module.lambda_ws_connect.function_arn  # reuse connect for auth
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
  source          = "../../modules/waf"
  env             = local.env
  api_gateway_arn = "arn:aws:apigateway:${var.region}::/restapis/${module.api_gateway_rest.api_id}/stages/dev"
}

# ============================================================
# REST API Gateway
# ============================================================
module "api_gateway_rest" {
  source               = "../../modules/api_gateway_rest"
  env                  = local.env
  region               = var.region
  alb_listener_arn     = "arn:aws:elasticloadbalancing:${var.region}:${local.account_id}:listener/app/${local.env}-alb/*"
  cognito_user_pool_id = module.cognito.user_pool_id
  cognito_client_id    = module.cognito.client_id
  private_subnet_ids   = module.networking.private_subnet_ids
  security_group_ids   = [module.networking.sg_ecs_id]
  allowed_origins      = ["http://localhost:3000"]
}
