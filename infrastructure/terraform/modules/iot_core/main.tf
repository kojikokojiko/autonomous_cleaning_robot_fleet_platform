locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

# ============================================================
# IoT Policy - Robot Permissions
# ============================================================
resource "aws_iot_policy" "robot" {
  name = "${local.name}-robot-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["iot:Connect"]
        Resource = "arn:aws:iot:${var.region}:${var.account_id}:client/$${iot:ClientId}"
      },
      {
        Effect = "Allow"
        Action = ["iot:Publish"]
        Resource = [
          "arn:aws:iot:${var.region}:${var.account_id}:topic/robot/$${iot:ClientId}/telemetry",
          "arn:aws:iot:${var.region}:${var.account_id}:topic/robot/$${iot:ClientId}/events",
          "arn:aws:iot:${var.region}:${var.account_id}:topic/robot/$${iot:ClientId}/command/ack"
        ]
      },
      {
        Effect = "Allow"
        Action = ["iot:Subscribe"]
        Resource = [
          "arn:aws:iot:${var.region}:${var.account_id}:topicfilter/robot/$${iot:ClientId}/command",
          "arn:aws:iot:${var.region}:${var.account_id}:topicfilter/robot/$${iot:ClientId}/mission",
          "arn:aws:iot:${var.region}:${var.account_id}:topicfilter/robot/$${iot:ClientId}/ota"
        ]
      },
      {
        Effect = "Allow"
        Action = ["iot:Receive"]
        Resource = [
          "arn:aws:iot:${var.region}:${var.account_id}:topic/robot/$${iot:ClientId}/command",
          "arn:aws:iot:${var.region}:${var.account_id}:topic/robot/$${iot:ClientId}/mission",
          "arn:aws:iot:${var.region}:${var.account_id}:topic/robot/$${iot:ClientId}/ota"
        ]
      }
    ]
  })
}

# ============================================================
# IoT Topic Rules
# ============================================================

# Telemetry → Kinesis
resource "aws_iot_topic_rule" "telemetry_to_kinesis" {
  name        = "${replace(local.name, "-", "_")}_telemetry_to_kinesis"
  description = "Route robot telemetry to Kinesis Data Stream"
  enabled     = true
  sql         = "SELECT *, topic(2) as robot_id FROM 'robot/+/telemetry'"
  sql_version = "2016-03-23"

  kinesis {
    role_arn      = var.iot_rule_role_arn
    stream_name   = var.kinesis_stream_name
    partition_key = "$${robot_id}"
  }

  error_action {
    cloudwatch_logs {
      log_group_name = "/robotops/${var.env}/iot/errors"
      role_arn       = var.iot_rule_role_arn
    }
  }
}

# Events → EventBridge
resource "aws_iot_topic_rule" "events_to_eventbridge" {
  name        = "${replace(local.name, "-", "_")}_events_to_eventbridge"
  description = "Route robot events to EventBridge"
  enabled     = true
  sql         = "SELECT *, topic(2) as robot_id FROM 'robot/+/events'"
  sql_version = "2016-03-23"

  cloudwatch_logs {
    log_group_name = "/robotops/${var.env}/iot/events"
    role_arn       = var.iot_rule_role_arn
  }

  error_action {
    cloudwatch_logs {
      log_group_name = "/robotops/${var.env}/iot/errors"
      role_arn       = var.iot_rule_role_arn
    }
  }
}

# CloudWatch log group for IoT errors
resource "aws_cloudwatch_log_group" "iot_errors" {
  name              = "/robotops/${var.env}/iot/errors"
  retention_in_days = 30
  tags              = local.tags
}

resource "aws_cloudwatch_log_group" "iot_events" {
  name              = "/robotops/${var.env}/iot/events"
  retention_in_days = 30
  tags              = local.tags
}
