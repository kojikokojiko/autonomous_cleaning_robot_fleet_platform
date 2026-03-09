output "api_endpoint"    { value = module.api_gateway_rest.api_endpoint }
output "ws_endpoint"     { value = module.api_gateway_websocket.endpoint }
output "alb_dns"         { value = module.ecs.alb_dns_name }
output "cognito_pool_id" { value = module.cognito.user_pool_id }
output "cognito_client"  { value = module.cognito.client_id }
