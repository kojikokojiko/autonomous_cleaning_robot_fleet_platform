locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

resource "aws_apigatewayv2_api" "ws" {
  name                       = "${local.name}-websocket-api"
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"
  tags                       = local.tags
}

# Integrations
resource "aws_apigatewayv2_integration" "connect" {
  api_id             = aws_apigatewayv2_api.ws.id
  integration_type   = "AWS_PROXY"
  integration_uri    = var.connect_lambda_arn
  integration_method = "POST"
}

resource "aws_apigatewayv2_integration" "disconnect" {
  api_id             = aws_apigatewayv2_api.ws.id
  integration_type   = "AWS_PROXY"
  integration_uri    = var.disconnect_lambda_arn
  integration_method = "POST"
}

resource "aws_apigatewayv2_integration" "default" {
  api_id             = aws_apigatewayv2_api.ws.id
  integration_type   = "AWS_PROXY"
  integration_uri    = var.default_lambda_arn
  integration_method = "POST"
}

# Routes
resource "aws_apigatewayv2_route" "connect" {
  api_id    = aws_apigatewayv2_api.ws.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.connect.id}"
}

resource "aws_apigatewayv2_route" "disconnect" {
  api_id    = aws_apigatewayv2_api.ws.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.disconnect.id}"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.ws.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.default.id}"
}

# Stage
resource "aws_apigatewayv2_stage" "main" {
  api_id      = aws_apigatewayv2_api.ws.id
  name        = var.env
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 500
    throttling_rate_limit  = 1000
  }

  tags = local.tags
}

# Lambda permissions
resource "aws_lambda_permission" "ws_connect" {
  statement_id  = "AllowWebSocketConnect"
  action        = "lambda:InvokeFunction"
  function_name = var.connect_lambda_arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ws.execution_arn}/*/*"
}

resource "aws_lambda_permission" "ws_disconnect" {
  statement_id  = "AllowWebSocketDisconnect"
  action        = "lambda:InvokeFunction"
  function_name = var.disconnect_lambda_arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ws.execution_arn}/*/*"
}
