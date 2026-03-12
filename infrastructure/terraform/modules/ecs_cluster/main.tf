locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

# ============================================================
# ECS Cluster
# ============================================================
resource "aws_ecs_cluster" "main" {
  name = "${local.name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.tags
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

# ============================================================
# Application Load Balancer
# ============================================================
resource "aws_lb" "main" {
  name               = "${local.name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.sg_alb_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.env == "prod"

  tags = local.tags
}

resource "aws_lb_target_group" "services" {
  for_each = var.services

  name        = substr("${local.name}-${each.key}", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }

  tags = local.tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "RobotOps Platform"
      status_code  = "200"
    }
  }
}

resource "aws_lb_listener_rule" "services" {
  for_each     = var.services
  listener_arn = aws_lb_listener.http.arn
  priority     = each.value.priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services[each.key].arn
  }

  condition {
    path_pattern {
      values = [each.value.path_pattern]
    }
  }
}

# ============================================================
# ECS Services
# ============================================================
resource "aws_ecs_task_definition" "services" {
  for_each = var.services

  family                   = "${local.name}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = var.ecs_task_execution_role_arn
  task_role_arn            = var.ecs_task_role_arn

  container_definitions = jsonencode([{
    name      = each.key
    image     = each.value.image
    essential = true
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]
    environment = [for k, v in each.value.environment : { name = k, value = v }]
    secrets     = [for k, v in each.value.secrets : { name = k, valueFrom = v }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/${local.name}/${each.key}"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "services" {
  for_each          = var.services
  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = 30
  tags              = local.tags
}

resource "aws_ecs_service" "services" {
  for_each = var.services

  name            = "${local.name}-${each.key}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.services[each.key].arn
  desired_count   = each.value.desired_count

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.sg_ecs_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.services[each.key].arn
    container_name   = each.key
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  tags = local.tags
}
