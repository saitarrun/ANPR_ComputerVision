variable "project_name" {
  type = string
}

variable "db_username" {
  type      = string
  sensitive = true
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "jwt_secret" {
  type      = string
  sensitive = true
}

variable "secret_key" {
  type      = string
  sensitive = true
}

variable "celery_encryption_key" {
  type      = string
  sensitive = true
}

variable "secrets_kms_key_id" {
  type = string
}
