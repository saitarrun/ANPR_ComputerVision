# Development Environment - Minimal Cost Configuration
# Goal: Fast feedback loop with minimal cost

environment = "dev"
aws_region  = "us-east-1"
project_name = "anpr"

# ==============================
# Networking
# ==============================
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b"]

# ==============================
# ECS Fargate (Minimal)
# ==============================
ecs_task_cpu              = 256           # Minimal
ecs_task_memory           = 512           # Minimal
ecs_desired_count         = 1             # Single task
ecs_min_capacity          = 1
ecs_max_capacity          = 2             # Limited scaling
container_image           = ""             # Set via CLI
container_port            = 8000

# ==============================
# RDS PostgreSQL (Single-AZ)
# ==============================
rds_instance_class        = "db.t3.small"
rds_allocated_storage     = 20            # 20 GB for dev
rds_storage_type          = "gp3"
rds_iops                  = 3000
rds_throughput            = 125
rds_engine_version        = "16.2"
rds_multi_az              = false         # No HA in dev
rds_backup_retention_days = 7             # Minimal retention

# ==============================
# ElastiCache Redis (Single-Node)
# ==============================
elasticache_node_type           = "cache.t3.micro"
elasticache_num_cache_nodes     = 1                    # Single node
elasticache_automatic_failover  = false                # No failover
elasticache_multi_az            = false
elasticache_parameter_group_family = "redis7"
elasticache_engine_version      = "7.0"

# ==============================
# S3 (No Optimization Overhead)
# ==============================
s3_bucket_versioning_enabled   = false
s3_bucket_encryption           = true
s3_bucket_public_access_block  = true

# Keep intelligent-tiering for storage efficiency
enable_intelligent_tiering     = true
s3_lifecycle_archive_days      = 30
s3_lifecycle_delete_days       = 90

# ==============================
# Cost Optimization Features (Disabled in Dev)
# ==============================
enable_cost_optimization       = false        # Skip optimization complexity
use_spot_instances             = false        # Not applicable
enable_scheduled_scaling       = false        # Keep 24/7 for testing

# ==============================
# Monitoring & Logging
# ==============================
enable_enhanced_monitoring     = false        # Reduced monitoring
log_retention_days             = 7            # Minimal retention
alarm_email                    = "dev@anpr.local"

# ==============================
# Tags
# ==============================
tags = {
  Environment = "dev"
  CostCenter  = "engineering"
  ManagedBy   = "terraform"
  CostOptimization = "disabled"
  Purpose     = "development-testing"
}
