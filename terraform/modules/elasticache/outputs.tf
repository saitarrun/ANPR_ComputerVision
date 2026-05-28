output "replication_group_id" {
  value = aws_elasticache_replication_group.main.id
}

output "primary_endpoint" {
  value = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "reader_endpoint" {
  value = aws_elasticache_replication_group.main.reader_endpoint_address
}

output "port" {
  value = aws_elasticache_replication_group.main.port
}

output "redis_security_group_id" {
  value = aws_security_group.redis.id
}
