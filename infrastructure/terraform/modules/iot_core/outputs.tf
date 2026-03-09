output "robot_policy_arn" {
  value = aws_iot_policy.robot.arn
}

output "iot_endpoint" {
  value = "data.iot.${var.region}.amazonaws.com"
}
