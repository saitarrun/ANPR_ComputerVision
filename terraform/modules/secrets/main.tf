# Database credentials
resource "aws_secretsmanager_secret" "db" {
  name                    = "${var.project_name}/database"
  description             = "PostgreSQL database credentials"
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-db-secret"
  }
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = var.db_username
    password = var.db_password
  })
}

# JWT signing key
resource "aws_secretsmanager_secret" "jwt" {
  name                    = "${var.project_name}/jwt"
  description             = "JWT signing secret"
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-jwt-secret"
  }
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id = aws_secretsmanager_secret.jwt.id
  secret_string = jsonencode({
    jwt_secret = var.jwt_secret
  })
}

# Application secrets
resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project_name}/app"
  description             = "Application encryption keys"
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-app-secret"
  }
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    secret_key = var.secret_key
  })
}

# Celery encryption key
resource "aws_secretsmanager_secret" "celery" {
  name                    = "${var.project_name}/celery"
  description             = "Celery message encryption key"
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-celery-secret"
  }
}

resource "aws_secretsmanager_secret_version" "celery" {
  secret_id = aws_secretsmanager_secret.celery.id
  secret_string = jsonencode({
    celery_encryption_key = var.celery_encryption_key
  })
}

# Rotation Lambda function for database password (RDS)
resource "aws_iam_role" "secrets_rotation" {
  name = "${var.project_name}-secrets-rotation"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-secrets-rotation-role"
  }
}

resource "aws_iam_role_policy_attachment" "secrets_rotation_basic" {
  role       = aws_iam_role.secrets_rotation.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "secrets_rotation_policy" {
  name = "${var.project_name}-secrets-rotation-policy"
  role = aws_iam_role.secrets_rotation.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GetSecret"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = aws_secretsmanager_secret.db.arn
      },
      {
        Sid    = "UpdateSecret"
        Effect = "Allow"
        Action = [
          "secretsmanager:UpdateSecretVersionStage",
          "secretsmanager:PutSecretValue"
        ]
        Resource = aws_secretsmanager_secret.db.arn
      }
    ]
  })
}

# Rotation for database secret (automatic password rotation every 30 days)
resource "aws_secretsmanager_secret_rotation" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  rotation_rules {
    automatically_after_days = 30
  }
  depends_on = [aws_secretsmanager_secret_version.db]
}

# JWT secret rotation (90-day schedule for long-lived signing keys)
resource "aws_secretsmanager_secret_rotation" "jwt" {
  secret_id = aws_secretsmanager_secret.jwt.id
  rotation_rules {
    automatically_after_days = 90
  }
  depends_on = [aws_secretsmanager_secret_version.jwt]
}

# App secret rotation (60-day schedule)
resource "aws_secretsmanager_secret_rotation" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  rotation_rules {
    automatically_after_days = 60
  }
  depends_on = [aws_secretsmanager_secret_version.app]
}

# KMS policy to allow Secrets Manager access
resource "aws_kms_key_policy" "secrets" {
  key_id = var.secrets_kms_key_id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM policies"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow Secrets Manager"
        Effect = "Allow"
        Principal = {
          Service = "secretsmanager.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = "*"
      }
    ]
  })
}

data "aws_caller_identity" "current" {}
