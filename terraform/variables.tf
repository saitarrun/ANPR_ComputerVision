variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name: dev, stage, prod"
  type        = string
  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "Environment must be dev, stage, or prod."
  }
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "anpr"
}

# ---- Networking ----
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# ---- Compute ----
variable "ecs_task_cpu" {
  description = "ECS task CPU units (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 1024
}

variable "ecs_task_memory" {
  description = "ECS task memory in MB (512, 1024, 2048, 4096, 8192)"
  type        = number
  default     = 2048
}

variable "ecs_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 2
  validation {
    condition     = var.ecs_desired_count >= 1 && var.ecs_desired_count <= 10
    error_message = "Desired count must be between 1 and 10."
  }
}

variable "ecs_min_capacity" {
  description = "Minimum number of ECS tasks for autoscaling"
  type        = number
  default     = 1
}

variable "ecs_max_capacity" {
  description = "Maximum number of ECS tasks for autoscaling"
  type        = number
  default     = 5
}

variable "container_image" {
  description = "Docker image URI (e.g., 123456789.dkr.ecr.us-east-1.amazonaws.com/anpr:latest)"
  type        = string
}

variable "container_port" {
  description = "Container port"
  type        = number
  default     = 8000
}

# ---- Database ----
variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.medium"
}

variable "rds_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "rds_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "16.2"
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ for high availability"
  type        = bool
  default     = true
}

variable "rds_backup_retention_days" {
  description = "Backup retention in days"
  type        = number
  default     = 7
  validation {
    condition     = var.rds_backup_retention_days >= 1 && var.rds_backup_retention_days <= 35
    error_message = "Backup retention must be between 1 and 35 days."
  }
}

# ---- Redis / ElastiCache ----
variable "elasticache_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t4g.micro"
}

variable "elasticache_num_cache_nodes" {
  description = "Number of cache nodes in the cluster"
  type        = number
  default     = 2
}

variable "elasticache_parameter_group_family" {
  description = "Redis parameter group family"
  type        = string
  default     = "redis7"
}

variable "elasticache_engine_version" {
  description = "Redis engine version"
  type        = string
  default     = "7.0"
}

# ---- S3 ----
variable "s3_bucket_versioning_enabled" {
  description = "Enable versioning on S3 buckets"
  type        = bool
  default     = true
}

variable "s3_bucket_encryption" {
  description = "Enable server-side encryption on S3 buckets"
  type        = bool
  default     = true
}

variable "s3_bucket_public_access_block" {
  description = "Block all public access to S3 buckets"
  type        = bool
  default     = true
}

# ---- Secrets ----
variable "database_username" {
  description = "RDS master username"
  type        = string
  sensitive   = true
}

variable "database_password" {
  description = "RDS master password (strong)"
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.database_password) >= 16 && can(regex("[A-Z]", var.database_password)) && can(regex("[a-z]", var.database_password)) && can(regex("[0-9]", var.database_password)) && can(regex("[!@#$%^&*()_+\\-=\\[\\]{};':\",./<>?]", var.database_password))
    error_message = "Password must be at least 16 chars with uppercase, lowercase, numbers, and special chars."
  }
}

variable "jwt_secret" {
  description = "JWT signing secret key"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "Fernet encryption key for app secrets"
  type        = string
  sensitive   = true
}

variable "celery_encryption_key" {
  description = "Encryption key for Celery messages"
  type        = string
  sensitive   = true
}

# ---- Monitoring ----
variable "enable_enhanced_monitoring" {
  description = "Enable detailed CloudWatch monitoring"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "alarm_email" {
  description = "Email for SNS alarm notifications"
  type        = string
}

# ---- Tags ----
variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
