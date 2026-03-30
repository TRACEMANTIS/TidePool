# =============================================================================
# S3 Buckets -- ALB Access Logs & Terraform State
# =============================================================================

# ===========================================================================
# ALB Access Logs Bucket
# ===========================================================================
# Both ALBs write access logs here, partitioned by prefix (tracking-alb/,
# dashboard-alb/).  Lifecycle policy transitions logs to Infrequent Access
# after 90 days and deletes them after 365 days.

resource "aws_s3_bucket" "alb_logs" {
  bucket = "${local.name_prefix}-alb-access-logs"

  # Prevent accidental deletion -- remove this for teardown
  force_destroy = false

  tags = {
    Name = "${local.name_prefix}-alb-access-logs"
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versioning (disabled for logs -- they are append-only)
resource "aws_s3_bucket_versioning" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id

  versioning_configuration {
    status = "Disabled"
  }
}

# Lifecycle: transition to IA at 90 days, expire at 365 days
resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id

  rule {
    id     = "log-lifecycle"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 365
    }
  }
}

# Bucket policy allowing ALB to write logs
resource "aws_s3_bucket_policy" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowALBLogDelivery"
        Effect = "Allow"
        Principal = {
          AWS = data.aws_elb_service_account.main.arn
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.alb_logs.arn}/*"
      },
      {
        Sid    = "AllowLogDeliveryService"
        Effect = "Allow"
        Principal = {
          Service = "delivery.logs.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.alb_logs.arn}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      },
      {
        Sid    = "AllowLogDeliveryAclCheck"
        Effect = "Allow"
        Principal = {
          Service = "delivery.logs.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.alb_logs.arn
      }
    ]
  })
}

# ===========================================================================
# Terraform State Bucket
# ===========================================================================
# This bucket stores remote state.  It must be created BEFORE running
# `terraform init` with the S3 backend configured in main.tf.
#
# Bootstrap procedure:
#   1. Comment out the backend "s3" block in main.tf
#   2. Run `terraform init` (uses local state)
#   3. Run `terraform apply -target=aws_s3_bucket.terraform_state -target=aws_dynamodb_table.terraform_locks`
#   4. Uncomment the backend block
#   5. Run `terraform init -migrate-state`

resource "aws_s3_bucket" "terraform_state" {
  bucket = "tidepool-terraform-state"

  force_destroy = false

  tags = {
    Name = "tidepool-terraform-state"
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled" # Required for state recovery
  }
}

# DynamoDB table for state locking
resource "aws_dynamodb_table" "terraform_locks" {
  name         = "tidepool-terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Name = "tidepool-terraform-locks"
  }
}
