resource "aws_security_group" "redis" {
  name        = "${var.project_name}-redis-sg"
  description = "Security group for ANPR Redis"
  vpc_id      = var.vpc_id

  # Allow from ECS tasks
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.ecs_security_group_id]
    description     = "Redis from ECS"
  }

  # Allow from Celery workers (same SG)
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.ecs_security_group_id]
    description     = "Redis from Celery"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-redis-sg"
  }
}

# Subnet group (private subnets only)
resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.project_name}-redis-subnet-group"
  }
}

# Parameter Group (enforce encryption, best practices)
resource "aws_elasticache_parameter_group" "main" {
  name        = "${var.project_name}-redis-params"
  family      = var.parameter_group_family
  description = "ANPR Redis parameter group"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru" # Evict least recently used when max memory reached
  }

  parameter {
    name  = "timeout"
    value = "300" # Close idle connections after 5 minutes
  }

  parameter {
    name  = "tcp-keepalive"
    value = "60" # TCP keepalive interval
  }

  tags = {
    Name = "${var.project_name}-redis-params"
  }
}

# KMS Key for Redis encryption
resource "aws_kms_key" "redis" {
  description             = "KMS key for ANPR Redis encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-redis-key"
  }
}

resource "aws_kms_alias" "redis" {
  name          = "alias/${var.project_name}-redis"
  target_key_id = aws_kms_key.redis.key_id
}

# Replication Group (1 primary + replica for HA)
resource "aws_elasticache_replication_group" "main" {
  replication_group_description = "ANPR Redis cluster (primary + replica)"
  engine                        = "redis"
  engine_version                = var.engine_version
  node_type                     = var.node_type
  num_cache_clusters            = var.num_cache_nodes
  parameter_group_name          = aws_elasticache_parameter_group.main.name
  subnet_group_name             = aws_elasticache_subnet_group.main.name
  security_group_ids            = [aws_security_group.redis.id]
  replication_group_id          = "${var.project_name}-redis"
  automatic_failover_enabled    = true
  multi_az_enabled              = true
  at_rest_encryption_enabled    = true
  transit_encryption_enabled    = true
  auth_token                    = var.redis_auth_token
  auth_token_update_strategy    = "ROTATE"
  kms_key_id                    = aws_kms_key.redis.arn

  # Maintenance
  maintenance_window = "sun:03:00-sun:04:00" # Sunday 3 AM UTC
  notification_topic_arn = var.sns_topic_arn

  # Backups
  snapshot_retention_limit = 5 # Keep last 5 snapshots
  snapshot_window          = "02:00-03:00" # 2 AM UTC

  # Logging
  log_delivery_configuration {
    destination      = var.cloudwatch_log_group_name
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    enabled          = true
  }

  tags = {
    Name = "${var.project_name}-redis"
  }

  depends_on = [aws_elasticache_parameter_group.main]
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "redis_cpu" {
  alarm_name          = "${var.project_name}-redis-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 75
  alarm_description   = "Alert when Redis CPU exceeds 75%"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.main.id
  }
}

resource "aws_cloudwatch_metric_alarm" "redis_memory" {
  alarm_name          = "${var.project_name}-redis-high-memory"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 85
  alarm_description   = "Alert when Redis memory exceeds 85%"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.main.id
  }
}

resource "aws_cloudwatch_metric_alarm" "redis_evictions" {
  alarm_name          = "${var.project_name}-redis-evictions"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Evictions"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Sum"
  threshold           = 100
  alarm_description   = "Alert when Redis evictions occur (cache pressure)"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.main.id
  }
}

resource "aws_cloudwatch_metric_alarm" "redis_swap" {
  alarm_name          = "${var.project_name}-redis-swap-usage"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "SwapUsage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 52428800 # 50 MB
  alarm_description   = "Alert when Redis swap usage exceeds 50 MB"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.main.id
  }
}
