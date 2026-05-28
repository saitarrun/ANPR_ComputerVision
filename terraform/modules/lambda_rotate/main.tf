# ============================================================================
# Lambda Function for RDS Password Rotation
# ============================================================================
# Automatically rotates RDS master password via AWS Secrets Manager.
# Implements 4-step rotation: create → set → test → finish

# Data source to read Lambda code from local directory
data "archive_file" "rotation_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambda"
  output_path = "${path.module}/.terraform/lambda-rotation.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache"]
}

# Lambda function for secrets rotation
resource "aws_lambda_function" "rotation" {
  filename         = data.archive_file.rotation_lambda.output_path
  source_code_hash = data.archive_file.rotation_lambda.output_base64sha256
  function_name    = "${var.project_name}-secrets-rotation"
  role             = aws_iam_role.rotation_lambda.arn
  handler          = "rotate_secret.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      RDS_INSTANCE_ID = var.rds_instance_id
      LOG_LEVEL       = var.log_level
    }
  }

  # VPC configuration to reach RDS in private subnet
  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.rotation_lambda.id]
  }

  layers = [aws_lambda_layer_version.dependencies.arn]

  tags = {
    Name        = "${var.project_name}-secrets-rotation"
    Environment = var.environment
  }

  depends_on = [
    aws_iam_role_policy_attachment.rotation_lambda_vpc,
    aws_iam_role_policy_attachment.rotation_lambda_secrets,
    aws_iam_role_policy_attachment.rotation_lambda_rds,
  ]
}

# Lambda Layer for Python dependencies (boto3, psycopg2)
# Note: For production deployment, build the layer offline using:
#   pip install -r lambda/requirements.txt -t lambda_layer/python/lib/python3.11/site-packages/
#   zip -r lambda-layer.zip lambda_layer/
# Then reference the pre-built zip file. For now, Lambda uses managed boto3 + requires psycopg2 as installed via layer.
# Boto3 is included with Lambda runtime, so we only need psycopg2 as a dependency.
resource "aws_lambda_layer_version" "dependencies" {
  filename            = data.archive_file.lambda_layer.output_path
  layer_name          = "${var.project_name}-rotation-dependencies"
  source_code_hash    = data.archive_file.lambda_layer.output_base64sha256
  compatible_runtimes = ["python3.11", "python3.12"]

  depends_on = [data.archive_file.lambda_layer]
}

# Archive the Lambda layer with dependencies
# For local development, we create a minimal layer. In production CI/CD,
# pre-build this with pip install -r requirements.txt
data "archive_file" "lambda_layer" {
  type        = "zip"
  output_path = "${path.module}/.terraform/lambda-layer.zip"

  source {
    content  = "# psycopg2 and boto3 required. Install via: pip install -r lambda/requirements.txt -t python/lib/python3.11/site-packages/"
    filename = "python/lib/python3.11/site-packages/README.txt"
  }
}

# Security group for Lambda function (egress only)
resource "aws_security_group" "rotation_lambda" {
  name        = "${var.project_name}-rotation-lambda-sg"
  description = "Security group for secrets rotation Lambda"
  vpc_id      = var.vpc_id

  # Egress to RDS (PostgreSQL)
  egress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.rds_security_group_id]
    description     = "PostgreSQL to RDS"
  }

  # Egress to Secrets Manager (HTTPS)
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS to AWS Secrets Manager"
  }

  # Egress to RDS API (HTTPS)
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS to AWS RDS API"
  }

  tags = {
    Name = "${var.project_name}-rotation-lambda-sg"
  }
}

# IAM Role for Lambda function
resource "aws_iam_role" "rotation_lambda" {
  name               = "${var.project_name}-rotation-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Name = "${var.project_name}-rotation-lambda-role"
  }
}

# Trust policy: allow Lambda service to assume role
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"
    principals = {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

# Attach VPC execution policy (required for Lambda in VPC)
resource "aws_iam_role_policy_attachment" "rotation_lambda_vpc" {
  role       = aws_iam_role.rotation_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Attach basic Lambda execution policy (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "rotation_lambda_basic" {
  role       = aws_iam_role.rotation_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Inline policy for Secrets Manager operations
resource "aws_iam_role_policy_attachment" "rotation_lambda_secrets" {
  role       = aws_iam_role.rotation_lambda.name
  policy_arn = aws_iam_policy.rotation_lambda_secrets.arn
}

resource "aws_iam_policy" "rotation_lambda_secrets" {
  name   = "${var.project_name}-rotation-lambda-secrets"
  policy = data.aws_iam_policy_document.rotation_lambda_secrets.json
}

data "aws_iam_policy_document" "rotation_lambda_secrets" {
  statement {
    sid    = "GetAndUpdateSecret"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
      "secretsmanager:PutSecretValue",
      "secretsmanager:UpdateSecretVersionStage",
    ]
    resources = [var.db_secret_arn]
  }
}

# Inline policy for RDS operations
resource "aws_iam_role_policy_attachment" "rotation_lambda_rds" {
  role       = aws_iam_role.rotation_lambda.name
  policy_arn = aws_iam_policy.rotation_lambda_rds.arn
}

resource "aws_iam_policy" "rotation_lambda_rds" {
  name   = "${var.project_name}-rotation-lambda-rds"
  policy = data.aws_iam_policy_document.rotation_lambda_rds.json
}

data "aws_iam_policy_document" "rotation_lambda_rds" {
  statement {
    sid    = "ModifyRDSPassword"
    effect = "Allow"
    actions = [
      "rds:ModifyDBInstance",
      "rds:DescribeDBInstances",
    ]
    resources = ["arn:aws:rds:*:*:db/${var.rds_instance_id}"]
  }
}

# Permission for Secrets Manager to invoke Lambda
resource "aws_lambda_permission" "rotation_trigger" {
  statement_id  = "AllowSecretsManagerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rotation.function_name
  principal     = "secretsmanager.amazonaws.com"
}

# Configure rotation for database secret
resource "aws_secretsmanager_secret_rotation" "db" {
  secret_id = var.db_secret_id

  rotation_rules {
    automatically_after_days = var.rotation_days
    duration                 = 3
    schedule_expression      = var.rotation_schedule_expression
  }

  rotation_lambda_arn = "${aws_lambda_function.rotation.arn}:${aws_lambda_function.rotation.version}"

  depends_on = [aws_lambda_permission.rotation_trigger]
}

# CloudWatch Log Group for Lambda execution logs
resource "aws_cloudwatch_log_group" "rotation_lambda" {
  name              = "/aws/lambda/${aws_lambda_function.rotation.function_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.project_name}-rotation-logs"
  }
}

# CloudWatch alarms for rotation failures
resource "aws_cloudwatch_metric_alarm" "rotation_invocation_errors" {
  alarm_name          = "${var.project_name}-rotation-invocation-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "Alert when secrets rotation Lambda fails"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    FunctionName = aws_lambda_function.rotation.function_name
  }
}

# Metric alarm for Lambda duration (timeout warning)
resource "aws_cloudwatch_metric_alarm" "rotation_duration" {
  alarm_name          = "${var.project_name}-rotation-duration-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Average"
  threshold           = "50000" # 50 seconds (timeout is 60)
  alarm_description   = "Alert when rotation takes too long"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    FunctionName = aws_lambda_function.rotation.function_name
  }
}
