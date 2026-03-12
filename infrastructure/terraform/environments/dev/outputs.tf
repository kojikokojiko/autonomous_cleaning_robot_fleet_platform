output "api_endpoint" { value = module.api_gateway_rest.api_endpoint }
output "ws_endpoint"  { value = module.api_gateway_websocket.endpoint }
output "alb_dns"      { value = module.ecs.alb_dns_name }

# GitHub Actions secrets / variables
output "github_actions_role_arn"     { value = aws_iam_role.github_actions.arn }
output "dashboard_bucket"            { value = module.cloudfront_dashboard.bucket_name }
output "cloudfront_distribution_id"  { value = module.cloudfront_dashboard.distribution_id }
output "dashboard_url"               { value = "https://${module.cloudfront_dashboard.domain_name}" }
output "account_id"                  { value = local.account_id }
