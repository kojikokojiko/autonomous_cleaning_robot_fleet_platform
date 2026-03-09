locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

resource "aws_kinesis_stream" "telemetry" {
  name             = "${local.name}-telemetry"
  shard_count      = var.shard_count
  retention_period = 24  # hours

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = local.tags
}

# CloudWatch alarms for Kinesis
resource "aws_cloudwatch_metric_alarm" "kinesis_write_exceeded" {
  alarm_name          = "${local.name}-kinesis-write-exceeded"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "WriteProvisionedThroughputExceeded"
  namespace           = "AWS/Kinesis"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Kinesis write throttling detected - consider adding shards"

  dimensions = {
    StreamName = aws_kinesis_stream.telemetry.name
  }

  tags = local.tags
}
