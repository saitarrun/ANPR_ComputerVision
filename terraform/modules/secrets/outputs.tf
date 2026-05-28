output "db_secret_arn" {
  value = aws_secretsmanager_secret.db.arn
}

output "jwt_secret_arn" {
  value = aws_secretsmanager_secret.jwt.arn
}

output "app_secret_arn" {
  value = aws_secretsmanager_secret.app.arn
}

output "celery_secret_arn" {
  value = aws_secretsmanager_secret.celery.arn
}

output "secrets_rotation_role_arn" {
  value       = aws_iam_role.secrets_rotation.arn
  description = "IAM role for Secrets Manager rotation Lambda"
}

output "rotation_schedule" {
  value = {
    db_password = "30 days"
    jwt_secret  = "90 days"
    app_secret  = "60 days"
  }
  description = "Automatic secret rotation schedule"
}
