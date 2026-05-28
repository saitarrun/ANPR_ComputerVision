# ============================================================================
# Production Environment Configuration
# ============================================================================

environment = "prod"
aws_region  = "us-east-1"

# VPC
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

# Compute (high availability)
ecs_task_cpu      = 2048
ecs_task_memory   = 4096
ecs_desired_count = 3
ecs_min_capacity  = 2
ecs_max_capacity  = 10
container_image   = "123456789.dkr.ecr.us-east-1.amazonaws.com/anpr:v1.0.0"
container_port    = 8000

# Database (HA with Multi-AZ)
rds_instance_class        = "db.r6g.xlarge"
rds_allocated_storage     = 100
rds_engine_version        = "16.2"
rds_multi_az              = true
rds_backup_retention_days = 30

# Redis (HA with replica)
elasticache_node_type       = "cache.r6g.xlarge"
elasticache_num_cache_nodes = 2

# S3
s3_bucket_versioning_enabled = true
s3_bucket_encryption         = true
s3_bucket_public_access_block = true

# Monitoring (full observability)
enable_enhanced_monitoring = true
log_retention_days         = 90
alarm_email                = "ops-alerts@yourdomain.com"
