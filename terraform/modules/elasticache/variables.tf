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

variable "node_type" {
  type = string
}

variable "num_cache_nodes" {
  type = number
}

variable "engine_version" {
  type = string
}

variable "parameter_group_family" {
  type = string
}

variable "redis_auth_token" {
  type      = string
  sensitive = true
}

variable "sns_topic_arn" {
  type = string
}

variable "cloudwatch_log_group_name" {
  type = string
}
