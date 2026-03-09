locals {
  name = "robotops-${var.env}"
  tags = {
    Project     = "robotops"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

# ============================================================
# Firmware Bucket
# ============================================================
resource "aws_s3_bucket" "firmware" {
  bucket = "${local.name}-firmware-${var.account_id}"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "firmware" {
  bucket = aws_s3_bucket.firmware.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "firmware" {
  bucket = aws_s3_bucket.firmware.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "firmware" {
  bucket                  = aws_s3_bucket.firmware.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================
# Maps Bucket
# ============================================================
resource "aws_s3_bucket" "maps" {
  bucket = "${local.name}-maps-${var.account_id}"
  tags   = local.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "maps" {
  bucket = aws_s3_bucket.maps.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "maps" {
  bucket                  = aws_s3_bucket.maps.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================
# Terraform State Bucket (prod only)
# ============================================================
resource "aws_s3_bucket" "terraform_state" {
  count  = var.create_terraform_state_bucket ? 1 : 0
  bucket = "robotops-terraform-state-${var.account_id}"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  count  = var.create_terraform_state_bucket ? 1 : 0
  bucket = aws_s3_bucket.terraform_state[0].id
  versioning_configuration { status = "Enabled" }
}

resource "aws_dynamodb_table" "terraform_lock" {
  count        = var.create_terraform_state_bucket ? 1 : 0
  name         = "robotops-terraform-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = local.tags
}
