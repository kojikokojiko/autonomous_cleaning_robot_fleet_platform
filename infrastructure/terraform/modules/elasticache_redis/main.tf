locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name}-redis-subnet-group"
  subnet_ids = var.private_subnet_ids
  tags       = local.tags
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${local.name}-redis"
  description          = "RobotOps Redis cache"

  node_type            = var.node_type
  num_cache_clusters   = var.env == "prod" ? 2 : 1
  port                 = 6379

  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [var.sg_redis_id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  automatic_failover_enabled = var.env == "prod"
  multi_az_enabled           = var.env == "prod"

  log_delivery_configuration {
    destination      = "/elasticache/${local.name}/slow-log"
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    log_type         = "slow-log"
  }

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "redis_slow_log" {
  name              = "/elasticache/${local.name}/slow-log"
  retention_in_days = 30
  tags              = local.tags
}
