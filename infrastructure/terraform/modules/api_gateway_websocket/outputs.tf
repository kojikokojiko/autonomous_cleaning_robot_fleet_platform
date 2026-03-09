output "api_id"       { value = aws_apigatewayv2_api.ws.id }
output "endpoint"     { value = aws_apigatewayv2_stage.main.invoke_url }
output "execution_arn" { value = aws_apigatewayv2_api.ws.execution_arn }
