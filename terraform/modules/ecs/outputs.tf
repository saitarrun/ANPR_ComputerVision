output "ecs_cluster_id" {
  value = aws_ecs_cluster.main.id
}

output "ecs_service_id" {
  value = aws_ecs_service.api.id
}

output "ecs_task_definition_arn" {
  value = aws_ecs_task_definition.api.arn
}

output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}

output "ecs_cloudwatch_log_group" {
  value = aws_cloudwatch_log_group.ecs.name
}
