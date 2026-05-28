output "lambda_function_arn" {
  value       = aws_lambda_function.rotation.arn
  description = "ARN of the secrets rotation Lambda function"
}

output "lambda_function_name" {
  value       = aws_lambda_function.rotation.function_name
  description = "Name of the secrets rotation Lambda function"
}

output "lambda_role_arn" {
  value       = aws_iam_role.rotation_lambda.arn
  description = "ARN of the Lambda execution role"
}

output "rotation_schedule" {
  value = {
    days_between_rotations  = var.rotation_days
    schedule_expression     = var.rotation_schedule_expression
    last_rotation_date      = aws_secretsmanager_secret_rotation.db.rotation_enabled ? "See AWS Console" : "Rotation not yet triggered"
  }
  description = "Rotation schedule configuration"
}

output "cloudwatch_log_group" {
  value       = aws_cloudwatch_log_group.rotation_lambda.name
  description = "CloudWatch log group for rotation Lambda"
}

output "security_group_id" {
  value       = aws_security_group.rotation_lambda.id
  description = "Security group ID for Lambda VPC placement"
}
