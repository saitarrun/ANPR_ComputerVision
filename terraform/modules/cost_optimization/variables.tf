# Cost Optimization Module Variables

variable "enable_cost_optimization" {
  description = "Enable cost optimization features (autoscaling, S3 lifecycle, VPC endpoints)"
  type        = bool
  default     = true
}

variable "enable_scheduled_scaling" {
  description = "Enable scheduled scaling (scale down 9pm-6am UTC)"
  type        = bool
  default     = false
}

variable "enable_intelligent_tiering" {
  description = "Enable S3 Intelligent-Tiering and lifecycle policies"
  type        = bool
  default     = true
}

# ==============================
# ECS Autoscaling Configuration
# ==============================

variable "ecs_min_capacity" {
  description = "Minimum number of ECS tasks (baseline)"
  type        = number
  validation {
    condition     = var.ecs_min_capacity >= 0 && var.ecs_min_capacity <= 10
    error_message = "Min capacity must be 0-10"
  }
}

variable "ecs_max_capacity" {
  description = "Maximum number of ECS tasks (peak)"
  type        = number
  validation {
    condition     = var.ecs_max_capacity >= 1 && var.ecs_max_capacity <= 20
    error_message = "Max capacity must be 1-20"
  }
}

variable "cluster_name" {
  description = "ECS cluster name"
  type        = string
}

variable "service_name" {
  description = "ECS service name"
  type        = string
}

variable "service_dependency" {
  description = "Dependency on ECS service (for ordering)"
  type        = any
  default     = null
}

# ==============================
# S3 Configuration
# ==============================

variable "s3_bucket_frames_id" {
  description = "S3 bucket ID for ANPR frames"
  type        = string
  default     = ""
}

variable "s3_bucket_crops_id" {
  description = "S3 bucket ID for plate crops"
  type        = string
  default     = ""
}

variable "s3_bucket_audit_id" {
  description = "S3 bucket ID for audit logs"
  type        = string
  default     = ""
}

variable "s3_lifecycle_archive_days" {
  description = "Days before archiving S3 objects to Glacier"
  type        = number
  default     = 30
  validation {
    condition     = var.s3_lifecycle_archive_days >= 1 && var.s3_lifecycle_archive_days <= 90
    error_message = "Archive days must be 1-90"
  }
}

variable "s3_lifecycle_delete_days" {
  description = "Days before deleting S3 objects (GDPR compliance)"
  type        = number
  default     = 90
  validation {
    condition     = var.s3_lifecycle_delete_days >= 1 && var.s3_lifecycle_delete_days <= 365
    error_message = "Delete days must be 1-365"
  }
}

# ==============================
# VPC Configuration
# ==============================

variable "vpc_id" {
  description = "VPC ID for VPC endpoints"
  type        = string
  default     = ""
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_route_table_ids" {
  description = "List of private route table IDs (for S3 endpoint)"
  type        = list(string)
  default     = []
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs (for CloudWatch Logs endpoint)"
  type        = list(string)
  default     = []
}

# ==============================
# Monitoring & Alerting
# ==============================

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for cost optimization alerts"
  type        = string
  default     = ""
}

# ==============================
# Tagging
# ==============================

variable "project_name" {
  description = "Project name (for tagging)"
  type        = string
  default     = "anpr"
}

variable "environment" {
  description = "Environment (dev/stage/prod)"
  type        = string
  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "Environment must be dev, stage, or prod"
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}
