variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "alb_security_group_id" {
  type = string
}

variable "alb_target_group_arn" {
  type = string
}

variable "alb_listener_arn" {
  type = string
}

variable "container_image" {
  type = string
}

variable "container_port" {
  type = number
}

variable "task_cpu" {
  type = number
}

variable "task_memory" {
  type = number
}

variable "desired_count" {
  type = number
}

variable "min_capacity" {
  type = number
}

variable "max_capacity" {
  type = number
}

variable "log_level" {
  type    = string
  default = "INFO"
}

variable "frontend_origins" {
  type = string
}

variable "api_workers" {
  type    = number
  default = 4
}

variable "rds_security_group_id" {
  type = string
}

variable "redis_security_group_id" {
  type = string
}

variable "db_secret_arn" {
  type = string
}

variable "jwt_secret_arn" {
  type = string
}

variable "app_secret_arn" {
  type = string
}

variable "celery_secret_arn" {
  type = string
}

variable "kms_key_arns" {
  type = list(string)
}

variable "db_proxy_endpoint" {
  type = string
}

variable "db_name" {
  type = string
}

variable "redis_endpoint" {
  type = string
}

variable "redis_auth_token" {
  type      = string
  sensitive = true
}

variable "aws_region" {
  type = string
}

variable "s3_bucket_frames" {
  type = string
}

variable "s3_bucket_crops" {
  type = string
}

variable "s3_bucket_audit" {
  type = string
}

variable "log_retention_days" {
  type = number
}

variable "otel_endpoint" {
  type = string
}
