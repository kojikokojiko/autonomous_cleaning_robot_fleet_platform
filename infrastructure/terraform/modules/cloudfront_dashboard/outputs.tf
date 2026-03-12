output "bucket_name"       { value = aws_s3_bucket.dashboard.bucket }
output "bucket_arn"        { value = aws_s3_bucket.dashboard.arn }
output "distribution_id"   { value = aws_cloudfront_distribution.dashboard.id }
output "domain_name"       { value = aws_cloudfront_distribution.dashboard.domain_name }
