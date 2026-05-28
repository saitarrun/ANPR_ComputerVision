variable "project_name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "ecs_security_group_id" {
  type = string
}

variable "allocated_storage" {
  type = number
}

variable "instance_class" {
  type = string
}

variable "engine_version" {
  type = string
}

variable "engine_version_major" {
  type = string
}

variable "master_username" {
  type      = string
  sensitive = true
}

variable "master_password" {
  type      = string
  sensitive = true
}

variable "multi_az" {
  type = bool
}

variable "backup_retention_days" {
  type = number
}

variable "enable_enhanced_monitoring" {
  type = bool
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "skip_final_snapshot" {
  type    = bool
  default = false
}

variable "db_secret_arn" {
  type = string
}

variable "sns_topic_arn" {
  type = string
}
