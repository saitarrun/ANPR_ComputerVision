# Cost Optimization Module for ANPR Infrastructure
# Provides autoscaling, scheduled scaling, S3 lifecycle, and VPC endpoints

# ==============================
# ECS API Service Autoscaling
# ==============================

resource "aws_appautoscaling_target" "ecs_api" {
  count              = var.enable_cost_optimization ? 1 : 0
  max_capacity       = var.ecs_max_capacity
  min_capacity       = var.ecs_min_capacity
  resource_id        = "service/${var.cluster_name}/${var.service_name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  depends_on = [var.service_dependency]
}

# CPU-based autoscaling: scale out at 70%, scale in at 40%
resource "aws_appautoscaling_policy" "ecs_cpu_scaling" {
  count              = var.enable_cost_optimization ? 1 : 0
  name               = "${var.service_name}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_api[0].resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_api[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_api[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_out_cooldown = 60   # Scale out quickly (1 min)
    scale_in_cooldown  = 300  # Scale in slowly (5 min)
  }
}

# Memory-based autoscaling: scale out at 80%
resource "aws_appautoscaling_policy" "ecs_memory_scaling" {
  count              = var.enable_cost_optimization ? 1 : 0
  name               = "${var.service_name}-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_api[0].resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_api[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_api[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value       = 80.0
    scale_out_cooldown = 60
    scale_in_cooldown  = 300
  }
}

# ==============================
# ECS Scheduled Scaling (Off-Peak)
# ==============================

# Scale down at 9 PM UTC (off-peak)
resource "aws_appautoscaling_scheduled_action" "scale_down_night" {
  count                  = var.enable_scheduled_scaling ? 1 : 0
  scheduled_action_name  = "${var.service_name}-scale-down-night"
  service_namespace      = "ecs"
  schedule               = "cron(21 * ? * * *)"  # 9 PM UTC
  resource_id            = try(aws_appautoscaling_target.ecs_api[0].resource_id, "")
  scalable_dimension     = "ecs:service:DesiredCount"
  timezone               = "UTC"

  scalable_target_action {
    min_capacity = 0
    max_capacity = 1
  }

  depends_on = [aws_appautoscaling_target.ecs_api]
}

# Scale up at 6 AM UTC (on-peak)
resource "aws_appautoscaling_scheduled_action" "scale_up_morning" {
  count                  = var.enable_scheduled_scaling ? 1 : 0
  scheduled_action_name  = "${var.service_name}-scale-up-morning"
  service_namespace      = "ecs"
  schedule               = "cron(6 * ? * * *)"  # 6 AM UTC
  resource_id            = try(aws_appautoscaling_target.ecs_api[0].resource_id, "")
  scalable_dimension     = "ecs:service:DesiredCount"
  timezone               = "UTC"

  scalable_target_action {
    min_capacity = var.ecs_min_capacity
    max_capacity = var.ecs_max_capacity
  }

  depends_on = [aws_appautoscaling_target.ecs_api]
}

# ==============================
# S3 Intelligent-Tiering
# ==============================

# Enable automatic movement to cheaper storage tiers
resource "aws_s3_bucket_intelligent_tiering_configuration" "frames" {
  count  = var.enable_intelligent_tiering && var.s3_bucket_frames_id != "" ? 1 : 0
  bucket = var.s3_bucket_frames_id
  name   = "${var.project_name}-frames-intelligent-tiering"

  tiering {
    days          = 30
    access_tier   = "ARCHIVE_ACCESS"      # Move to S3 IA after 30 days
  }

  tiering {
    days          = 90
    access_tier   = "DEEP_ARCHIVE_ACCESS" # Move to Glacier after 90 days
  }

  status = "Enabled"
}

resource "aws_s3_bucket_intelligent_tiering_configuration" "crops" {
  count  = var.enable_intelligent_tiering && var.s3_bucket_crops_id != "" ? 1 : 0
  bucket = var.s3_bucket_crops_id
  name   = "${var.project_name}-crops-intelligent-tiering"

  tiering {
    days          = 30
    access_tier   = "ARCHIVE_ACCESS"
  }

  tiering {
    days          = 90
    access_tier   = "DEEP_ARCHIVE_ACCESS"
  }

  status = "Enabled"
}

# ==============================
# S3 Lifecycle Policies
# ==============================

# Frames: Archive after 30 days, delete after 90 days (GDPR compliance)
resource "aws_s3_bucket_lifecycle_configuration" "frames" {
  count  = var.enable_intelligent_tiering && var.s3_bucket_frames_id != "" ? 1 : 0
  bucket = var.s3_bucket_frames_id

  rule {
    id     = "archive-old-frames"
    status = "Enabled"

    filter {
      prefix = "frames/"
    }

    # Transition to Glacier for archival
    transition {
      days          = var.s3_lifecycle_archive_days
      storage_class = "GLACIER"
    }

    # Delete after retention period (GDPR: 90 days default)
    expiration {
      days = var.s3_lifecycle_delete_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.s3_lifecycle_delete_days
    }
  }

  depends_on = [aws_s3_bucket_intelligent_tiering_configuration.frames]
}

# Crops: Archive after 30 days, delete after 1 year
resource "aws_s3_bucket_lifecycle_configuration" "crops" {
  count  = var.enable_intelligent_tiering && var.s3_bucket_crops_id != "" ? 1 : 0
  bucket = var.s3_bucket_crops_id

  rule {
    id     = "archive-old-crops"
    status = "Enabled"

    filter {
      prefix = "crops/"
    }

    transition {
      days          = var.s3_lifecycle_archive_days
      storage_class = "GLACIER"
    }

    # Longer retention for crops (evidence/audit)
    expiration {
      days = 365
    }

    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }

  depends_on = [aws_s3_bucket_intelligent_tiering_configuration.crops]
}

# Audit logs: Archive after 30 days, keep for 3 years
resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  count  = var.enable_intelligent_tiering && var.s3_bucket_audit_id != "" ? 1 : 0
  bucket = var.s3_bucket_audit_id

  rule {
    id     = "archive-audit-logs"
    status = "Enabled"

    filter {
      prefix = "audit/"
    }

    # Compliance: keep audit logs for 3 years minimum
    transition {
      days          = 30
      storage_class = "GLACIER"
    }

    expiration {
      days = 1095  # 3 years
    }
  }
}

# ==============================
# VPC Endpoint for S3 (Bypass NAT)
# ==============================

# Gateway endpoint: saves NAT data transfer costs ($0.045/GB)
resource "aws_vpc_endpoint" "s3" {
  count             = var.enable_cost_optimization && var.vpc_id != "" ? 1 : 0
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids

  tags = {
    Name        = "${var.project_name}-s3-endpoint"
    Environment = var.environment
    CostOptimization = "true"
  }
}

# VPC Endpoint for CloudWatch Logs (optional, for stability)
resource "aws_vpc_endpoint" "cloudwatch" {
  count               = var.enable_cost_optimization && var.vpc_id != "" ? 1 : 0
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]

  private_dns_enabled = true

  tags = {
    Name        = "${var.project_name}-logs-endpoint"
    Environment = var.environment
  }
}

# Security group for VPC endpoints
resource "aws_security_group" "vpc_endpoints" {
  count           = var.enable_cost_optimization && var.vpc_id != "" ? 1 : 0
  name            = "${var.project_name}-vpc-endpoints-sg"
  description     = "Security group for VPC endpoints"
  vpc_id          = var.vpc_id

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    cidr_blocks     = [var.vpc_cidr]
    description     = "HTTPS from VPC"
  }

  egress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    cidr_blocks     = ["0.0.0.0/0"]
    description     = "All traffic out"
  }

  tags = {
    Name = "${var.project_name}-vpc-endpoints-sg"
  }
}

# ==============================
# Cost Optimization Tags
# ==============================

# Local for consistent tagging
locals {
  cost_optimization_tags = {
    CostOptimizationEnabled = var.enable_cost_optimization
    ScheduledScalingEnabled = var.enable_scheduled_scaling
    IntelligentTieringEnabled = var.enable_intelligent_tiering
    CreatedBy = "Terraform"
  }
}

# ==============================
# CloudWatch Alarms for Optimization
# ==============================

# Alert if autoscaling is not working (CPU stays high despite multiple tasks)
resource "aws_cloudwatch_metric_alarm" "cpu_not_scaling" {
  count             = var.enable_cost_optimization ? 1 : 0
  alarm_name        = "${var.service_name}-cpu-not-scaling"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods = 2
  metric_name       = "CPUUtilization"
  namespace         = "AWS/ECS"
  period            = 300
  statistic         = "Average"
  threshold         = 85
  alarm_description = "Alert if ECS CPU > 85% (scaling may be failing)"
  alarm_actions     = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    ServiceName = var.service_name
    ClusterName = var.cluster_name
  }
}

# Alert if S3 objects are not being archived (lifecycle may be failing)
resource "aws_cloudwatch_metric_alarm" "s3_objects_old" {
  count             = var.enable_intelligent_tiering && var.s3_bucket_frames_id != "" ? 1 : 0
  alarm_name        = "${var.project_name}-s3-old-objects"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods = 1
  metric_name       = "NumberOfObjects"
  namespace         = "AWS/S3"
  period            = 86400  # Daily
  statistic         = "Average"
  threshold         = 10000  # Alert if >10k old objects
  alarm_description = "Alert if many objects not archived (lifecycle job may be failing)"
  alarm_actions     = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    BucketName = var.s3_bucket_frames_id
    StorageType = "StandardStorageType"
  }
}
