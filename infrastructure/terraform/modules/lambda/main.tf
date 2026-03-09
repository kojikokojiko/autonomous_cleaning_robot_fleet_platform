locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

resource "aws_lambda_function" "this" {
  function_name = "${local.name}-${var.function_name}"
  description   = var.description
  role          = var.lambda_role_arn
  handler       = var.handler
  runtime       = var.runtime
  timeout       = var.timeout
  memory_size   = var.memory_size
  filename      = var.zip_path

  source_code_hash = filebase64sha256(var.zip_path)

  environment {
    variables = var.environment_variables
  }

  dynamic "vpc_config" {
    for_each = var.vpc_subnet_ids != null ? [1] : []
    content {
      subnet_ids         = var.vpc_subnet_ids
      security_group_ids = var.vpc_security_group_ids
    }
  }

  dead_letter_config {
    target_arn = var.dlq_arn
  }

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}-${var.function_name}"
  retention_in_days = 30
  tags              = local.tags
}

# Kinesis trigger (optional)
resource "aws_lambda_event_source_mapping" "kinesis" {
  count             = var.kinesis_stream_arn != null ? 1 : 0
  event_source_arn  = var.kinesis_stream_arn
  function_name     = aws_lambda_function.this.arn
  starting_position = "LATEST"
  batch_size        = var.kinesis_batch_size

  destination_config {
    on_failure {
      destination_arn = var.dlq_arn
    }
  }
}
