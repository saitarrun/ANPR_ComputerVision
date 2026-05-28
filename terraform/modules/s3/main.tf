locals {
  buckets = {
    frames = {
      name    = var.s3_bucket_frames
      purpose = "Frame storage"
    }
    crops = {
      name    = var.s3_bucket_crops
      purpose = "Cropped plate images"
    }
    audit = {
      name    = var.s3_bucket_audit
      purpose = "Audit logs"
    }
  }
}

# KMS Key for S3 encryption
resource "aws_kms_key" "s3" {
  description             = "KMS key for ANPR S3 bucket encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-s3-key"
  }
}

resource "aws_kms_alias" "s3" {
  name          = "alias/${var.project_name}-s3"
  target_key_id = aws_kms_key.s3.key_id
}

# Create S3 buckets with encryption, versioning, and lifecycle policies
resource "aws_s3_bucket" "main" {
  for_each = local.buckets
  bucket   = "${each.value.name}-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name    = each.value.name
    Purpose = each.value.purpose
  }
}

# Versioning
resource "aws_s3_bucket_versioning" "main" {
  for_each = aws_s3_bucket.main
  bucket   = each.value.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-Side Encryption (SSE-KMS)
resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  for_each = aws_s3_bucket.main
  bucket   = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "main" {
  for_each = aws_s3_bucket.main
  bucket   = each.value.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle policies
resource "aws_s3_bucket_lifecycle_configuration" "main" {
  for_each = aws_s3_bucket.main
  bucket   = each.value.id

  rule {
    id     = "archive-old-objects"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    expiration {
      days = 365
    }
  }

  rule {
    id     = "delete-incomplete-multipart"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Bucket policies (least privilege)
resource "aws_s3_bucket_policy" "main" {
  for_each = aws_s3_bucket.main
  bucket   = each.value.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyUnencryptedObjectUploads"
        Effect = "Deny"
        Principal = "*"
        Action = "s3:PutObject"
        Resource = "${aws_s3_bucket.main[each.key].arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = "aws:kms"
          }
        }
      },
      {
        Sid    = "DenyInsecureTransport"
        Effect = "Deny"
        Principal = "*"
        Action = "s3:*"
        Resource = [
          aws_s3_bucket.main[each.key].arn,
          "${aws_s3_bucket.main[each.key].arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# Enable logging for audit trail
resource "aws_s3_bucket_logging" "main" {
  for_each = aws_s3_bucket.main
  bucket   = each.value.id

  target_bucket = aws_s3_bucket.logging.id
  target_prefix = "logs/${each.value.id}/"
}

# Logging bucket (store logs here)
resource "aws_s3_bucket" "logging" {
  bucket = "${var.project_name}-s3-logs-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "${var.project_name}-s3-logs"
  }
}

resource "aws_s3_bucket_versioning" "logging" {
  bucket = aws_s3_bucket.logging.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "logging" {
  bucket = aws_s3_bucket.logging.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_caller_identity" "current" {}
