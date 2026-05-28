locals {
  db_name = replace(var.project_name, "-", "_")
}

# Parameter Group (enforce SSL, strict security settings)
resource "aws_db_parameter_group" "main" {
  name        = "${var.project_name}-params"
  family      = "postgres${var.engine_version_major}"
  description = "ANPR PostgreSQL parameter group"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # Log queries > 1000ms
  }

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  parameter {
    name  = "pgaudit.log"
    value = "DDL,DML,ROLE" # Audit CREATE/UPDATE/DELETE/grants
  }

  tags = {
    Name = "${var.project_name}-db-params"
  }
}

# DB Subnet Group (private subnets only)
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.project_name}-db-subnet-group"
  }
}

# RDS Proxy security group
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for ANPR RDS"
  vpc_id      = var.vpc_id

  # Allow from ECS tasks only
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.ecs_security_group_id]
    description     = "PostgreSQL from ECS"
  }

  # Allow from Celery workers (same SG as ECS or separate)
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.ecs_security_group_id]
    description     = "PostgreSQL from Celery"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = {
    Name = "${var.project_name}-rds-sg"
  }
}

# RDS Instance
resource "aws_db_instance" "main" {
  identifier            = "${var.project_name}-db"
  allocated_storage     = var.allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.rds.arn
  engine                = "postgres"
  engine_version        = var.engine_version
  instance_class        = var.instance_class
  db_name               = local.db_name
  username              = var.master_username
  password              = var.master_password
  parameter_group_name  = aws_db_parameter_group.main.name
  db_subnet_group_name  = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # High Availability
  multi_az = var.multi_az

  # Backups
  backup_retention_period = var.backup_retention_days
  backup_window           = "03:00-04:00" # 3 AM UTC (adjust for your TZ)
  copy_tags_to_snapshot   = true
  delete_automated_backups = false

  # Maintenance
  maintenance_window          = "mon:04:00-mon:05:00" # Monday 4 AM UTC
  auto_minor_version_upgrade  = true
  deletion_protection         = var.deletion_protection
  skip_final_snapshot         = var.skip_final_snapshot
  final_snapshot_identifier   = var.skip_final_snapshot ? null : "${var.project_name}-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  # Monitoring
  enabled_cloudwatch_logs_exports = ["postgresql"]
  monitoring_interval             = var.enable_enhanced_monitoring ? 60 : 0
  monitoring_role_arn             = var.enable_enhanced_monitoring ? aws_iam_role.rds_monitoring[0].arn : null
  performance_insights_enabled    = var.enable_enhanced_monitoring
  performance_insights_retention_period = var.enable_enhanced_monitoring ? 7 : null

  # Security
  publicly_accessible = false

  tags = {
    Name = "${var.project_name}-db"
  }

  depends_on = [aws_security_group.rds]
}

# KMS Key for RDS encryption
resource "aws_kms_key" "rds" {
  description             = "KMS key for ANPR RDS encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-rds-key"
  }
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.project_name}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

# IAM Role for Enhanced Monitoring
resource "aws_iam_role" "rds_monitoring" {
  count = var.enable_enhanced_monitoring ? 1 : 0
  name  = "${var.project_name}-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "monitoring.rds.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  count      = var.enable_enhanced_monitoring ? 1 : 0
  role       = aws_iam_role.rds_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# RDS Proxy for connection pooling (reduces connection exhaustion)
resource "aws_db_proxy" "main" {
  name                   = "${var.project_name}-proxy"
  engine_family          = "POSTGRESQL"
  auth {
    auth_scheme = "SECRETS"
    secret_arn  = var.db_secret_arn
  }
  role_arn               = aws_iam_role.proxy.arn
  max_idle_connections   = 10
  max_connections        = 100
  connection_borrow_timeout = 120
  session_pinning_filters = ["EXCLUDE_VARIABLE_SETS"] # Avoid sticky connections

  target {
    db_instance_identifier = aws_db_instance.main.identifier
  }

  tags = {
    Name = "${var.project_name}-proxy"
  }

  depends_on = [aws_iam_role_policy.proxy]
}

# IAM Role for RDS Proxy
resource "aws_iam_role" "proxy" {
  name = "${var.project_name}-rds-proxy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "rds.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "proxy" {
  name = "${var.project_name}-rds-proxy-policy"
  role = aws_iam_role.proxy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = var.db_secret_arn
    }]
  })
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "db_cpu" {
  alarm_name          = "${var.project_name}-db-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Alert when RDS CPU exceeds 80%"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }
}

resource "aws_cloudwatch_metric_alarm" "db_storage" {
  alarm_name          = "${var.project_name}-db-low-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 2147483648 # 2 GB
  alarm_description   = "Alert when free storage < 2 GB"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }
}

resource "aws_cloudwatch_metric_alarm" "db_connections" {
  alarm_name          = "${var.project_name}-db-high-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Alert when DB connections > 80"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }
}
