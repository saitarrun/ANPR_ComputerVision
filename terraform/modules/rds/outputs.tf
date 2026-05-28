output "db_instance_id" {
  value = aws_db_instance.main.id
}

output "db_instance_endpoint" {
  value = aws_db_instance.main.endpoint
  description = "Database endpoint (host:port)"
}

output "db_instance_address" {
  value = aws_db_instance.main.address
}

output "db_instance_port" {
  value = aws_db_instance.main.port
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "proxy_endpoint" {
  value = aws_db_proxy.main.endpoint
  description = "RDS Proxy endpoint (connection pooling)"
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "kms_key_id" {
  value = aws_kms_key.rds.key_id
}
