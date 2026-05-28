# Stage Environment - Production-Like with Cost Controls
# Goal: Validate production configuration without peak costs

environment = "stage"

# AWS Configuration
aws_region = "us-east-1"
project_name = "anpr"

# ==============================
# Networking
# ==============================
vpc_cidr = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b"]

# ==============================
# ECS Fargate (Production-Like)
# ==============================
ecs_task_cpu              = 512          # Slightly larger than prod for load testing
ecs_task_memory           = 1024         # 1 GB for margin during testing
ecs_desired_count         = 2            # 2 tasks baseline (HA-like)
ecs_min_capacity          = 1
ecs_max_capacity          = 4            # Lower max for cost control

container_port            = 8000
container_image           = ""            # Set via CLI

# ==============================
# RDS PostgreSQL (HA-Like)
# ==============================
rds_instance_class        = "db.t3.medium"    # Larger than prod for testing headroom
rds_allocated_storage     = 50               # 50 GB for stage
rds_storage_type          = "gp3"
rds_iops                  = 3000
rds_throughput            = 125
rds_engine_version        = "16.2"
rds_multi_az              = true             # HA for stage (test failover)
rds_backup_retention_days = 7                # Shorter retention to save cost

# ==============================
# ElastiCache Redis (Multi-Node for HA Testing)
# ==============================
elasticache_node_type          = "cache.t3.small"      # Larger for testing
elasticache_num_cache_nodes    = 2                     # 2 nodes (test failover)
elasticache_automatic_failover = true                  # Enable for HA testing
elasticache_multi_az           = true
elasticache_parameter_group_family = "redis7"
elasticache_engine_version     = "7.0"

# ==============================
# S3 (Intelligent-Tiering + Lifecycle)
# ==============================
s3_bucket_versioning_enabled   = false
s3_bucket_encryption           = true
s3_bucket_public_access_block  = true

# Cost Optimization: Enabled for demo
enable_intelligent_tiering     = true
s3_lifecycle_archive_days      = 30
s3_lifecycle_delete_days       = 90

# ==============================
# Cost Optimization Features
# ==============================
enable_cost_optimization       = true         # Enable for demo
use_spot_instances             = false        # Keep on-demand for stability
enable_scheduled_scaling       = false        # Keep stable for testing
# (Can enable scheduled scaling if testing off-peak scenarios)

# ==============================
# Monitoring & Logging
# ==============================
enable_enhanced_monitoring     = true
log_retention_days             = 30
alarm_email                    = "ops@anpr.local"

# ==============================
# Tags
# ==============================
tags = {
  Environment      = "stage"
  CostCenter       = "engineering"
  ManagedBy        = "terraform"
  CostOptimization = "enabled"
  Purpose          = "production-validation"
}
