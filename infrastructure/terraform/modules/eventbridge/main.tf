locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

# ============================================================
# Event Bus
# ============================================================
resource "aws_cloudwatch_event_bus" "robotops" {
  name = "${local.name}-event-bus"
  tags = local.tags
}

# ============================================================
# Event Rules
# ============================================================

# Battery Low → Alert Service (Lambda)
resource "aws_cloudwatch_event_rule" "battery_low" {
  name           = "${local.name}-battery-low"
  event_bus_name = aws_cloudwatch_event_bus.robotops.name
  description    = "Trigger alert when robot battery is low"

  event_pattern = jsonencode({
    source      = ["robotops.robot"]
    detail-type = ["RobotBatteryLow"]
  })

  tags = local.tags
}

resource "aws_cloudwatch_event_target" "battery_low_lambda" {
  rule           = aws_cloudwatch_event_rule.battery_low.name
  event_bus_name = aws_cloudwatch_event_bus.robotops.name
  target_id      = "AlertLambda"
  arn            = var.alert_lambda_arn
}

# Robot Stuck → Alert Service
resource "aws_cloudwatch_event_rule" "robot_stuck" {
  name           = "${local.name}-robot-stuck"
  event_bus_name = aws_cloudwatch_event_bus.robotops.name
  description    = "Trigger alert when robot is stuck"

  event_pattern = jsonencode({
    source      = ["robotops.robot"]
    detail-type = ["RobotStuck"]
  })

  tags = local.tags
}

resource "aws_cloudwatch_event_target" "robot_stuck_lambda" {
  rule           = aws_cloudwatch_event_rule.robot_stuck.name
  event_bus_name = aws_cloudwatch_event_bus.robotops.name
  target_id      = "AlertLambda"
  arn            = var.alert_lambda_arn
}

# Collision Detected → Alert Service
resource "aws_cloudwatch_event_rule" "collision" {
  name           = "${local.name}-collision-detected"
  event_bus_name = aws_cloudwatch_event_bus.robotops.name

  event_pattern = jsonencode({
    source      = ["robotops.robot"]
    detail-type = ["CollisionDetected"]
  })

  tags = local.tags
}

resource "aws_cloudwatch_event_target" "collision_lambda" {
  rule           = aws_cloudwatch_event_rule.collision.name
  event_bus_name = aws_cloudwatch_event_bus.robotops.name
  target_id      = "AlertLambda"
  arn            = var.alert_lambda_arn
}

# All robot events → WebSocket push
resource "aws_cloudwatch_event_rule" "all_robot_events" {
  name           = "${local.name}-all-robot-events"
  event_bus_name = aws_cloudwatch_event_bus.robotops.name
  description    = "Forward all robot events to WebSocket pusher"

  event_pattern = jsonencode({
    source = ["robotops.robot"]
  })

  tags = local.tags
}

resource "aws_cloudwatch_event_target" "ws_pusher_lambda" {
  rule           = aws_cloudwatch_event_rule.all_robot_events.name
  event_bus_name = aws_cloudwatch_event_bus.robotops.name
  target_id      = "WebSocketPusher"
  arn            = var.ws_pusher_lambda_arn
}

# Lambda permissions
resource "aws_lambda_permission" "eventbridge_alert" {
  statement_id  = "AllowEventBridgeAlert"
  action        = "lambda:InvokeFunction"
  function_name = var.alert_lambda_arn
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_bus.robotops.arn
}

resource "aws_lambda_permission" "eventbridge_ws_pusher" {
  statement_id  = "AllowEventBridgeWsPusher"
  action        = "lambda:InvokeFunction"
  function_name = var.ws_pusher_lambda_arn
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_bus.robotops.arn
}
