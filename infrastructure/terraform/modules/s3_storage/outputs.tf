output "firmware_bucket_name" { value = aws_s3_bucket.firmware.bucket }
output "firmware_bucket_arn"  { value = aws_s3_bucket.firmware.arn }
output "maps_bucket_name"     { value = aws_s3_bucket.maps.bucket }
output "maps_bucket_arn"      { value = aws_s3_bucket.maps.arn }
