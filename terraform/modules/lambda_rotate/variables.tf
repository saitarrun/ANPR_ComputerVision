variable "project_name" {
  type        = string
  description = "Project name (used for resource naming)"
}

variable "environment" {
  type        = string
  description = "Environment (dev, staging, prod)"
  default     = "prod"
}

variable "rds_instance_id" {
  type        = string
  description = "RDS instance identifier to rotate password for"
  sensitive   = true
}

variable "db_secret_id" {
  type        = string
  description = "AWS Secrets Manager secret ID for database credentials"
}

variable "db_secret_arn" {
  type        = string
  description = "AWS Secrets Manager secret ARN for database credentials"
}

variable "rds_security_group_id" {
  type        = string
  description = "Security group ID of RDS instance (for Lambda egress)"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where Lambda will run"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "List of private subnet IDs for Lambda VPC placement"
}

variable "rotation_days" {
  type        = number
  description = "Number of days between automatic rotations"
  default     = 30

  validation {
    condition     = var.rotation_days >= 1 && var.rotation_days <= 365
    error_message = "rotation_days must be between 1 and 365"
  }
}

variable "rotation_schedule_expression" {
  type        = string
  description = "Cron expression for rotation timing (optional)"
  default     = ""
}

variable "log_level" {
  type        = string
  description = "Lambda function log level"
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be one of: DEBUG, INFO, WARNING, ERROR"
  }
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention in days"
  default     = 30

  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653
    ], var.log_retention_days)
    error_message = "log_retention_days must be a valid CloudWatch retention period"
  }
}

variable "sns_topic_arn" {
  type        = string
  description = "SNS topic ARN for rotation failure alerts"
}
