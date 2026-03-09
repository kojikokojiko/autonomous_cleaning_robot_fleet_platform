locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

resource "aws_sqs_queue" "dlq" {
  name                       = "${local.name}-${var.queue_name}-dlq"
  message_retention_seconds  = 1209600  # 14 days
  visibility_timeout_seconds = 300

  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${local.name}-${var.queue_name}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "DLQ has messages - investigate Lambda processing failures"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  tags = local.tags
}
