output "robot_policy_arn" {
  value = aws_iot_policy.robot.arn
}

output "iot_endpoint" {
  value = data.aws_iot_endpoint.current.endpoint_address
}

output "fleet_template_name" {
  value = aws_iot_provisioning_template.fleet.name
}

output "claim_policy_name" {
  value = aws_iot_policy.claim.name
}

output "fleet_thing_group_name" {
  value = aws_iot_thing_group.fleet.name
}
