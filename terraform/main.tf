# ============================================================================
# ANPR Infrastructure-as-Code: Main Orchestration
# ============================================================================
#
# Orchestrates all infrastructure components:
# - VPC (networking, subnets, NAT, security)
# - RDS PostgreSQL (Multi-AZ, automated backups, connection pooling)
# - ElastiCache Redis (failover, encryption)
# - ECS Fargate (API container, auto-scaling)
# - Application Load Balancer (HTTPS, health checks)
# - S3 buckets (encryption, versioning, lifecycle)
# - AWS Secrets Manager (rotation)
# - CloudWatch (monitoring, alarms)
#
# Deployment: terraform init && terraform plan && terraform apply
# ============================================================================

module "monitoring" {
  source = "./modules/monitoring"

  project_name       = var.project_name
  alarm_email        = var.alarm_email
  aws_region         = var.aws_region
  log_retention_days = var.log_retention_days
}

module "vpc" {
  source = "./modules/vpc"

  project_name       = var.project_name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  log_retention_days = var.log_retention_days
}

module "secrets" {
  source = "./modules/secrets"

  project_name          = var.project_name
  db_username           = var.database_username
  db_password           = var.database_password
  jwt_secret            = var.jwt_secret
  secret_key            = var.secret_key
  celery_encryption_key = var.celery_encryption_key
  secrets_kms_key_id    = aws_kms_key.secrets.id
}

module "lambda_rotate" {
  source = "./modules/lambda_rotate"

  project_name           = var.project_name
  environment            = var.environment
  rds_instance_id        = module.rds.db_instance_id
  db_secret_id           = module.secrets.db_secret_id
  db_secret_arn          = module.secrets.db_secret_arn
  rds_security_group_id  = module.rds.rds_security_group_id
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnet_ids
  rotation_days          = 30
  log_level              = var.environment == "prod" ? "WARNING" : "INFO"
  log_retention_days     = var.log_retention_days
  sns_topic_arn          = module.monitoring.sns_topic_arn
}

module "s3" {
  source = "./modules/s3"

  project_name     = var.project_name
  s3_bucket_frames = "${var.project_name}-frames"
  s3_bucket_crops  = "${var.project_name}-crops"
  s3_bucket_audit  = "${var.project_name}-audit"
}

module "alb" {
  source = "./modules/alb"

  project_name        = var.project_name
  vpc_id              = module.vpc.vpc_id
  public_subnet_ids   = module.vpc.public_subnet_ids
  container_port      = var.container_port
  acm_certificate_arn = aws_acm_certificate.main.arn
  sns_topic_arn       = module.monitoring.sns_topic_arn
}

module "rds" {
  source = "./modules/rds"

  project_name           = var.project_name
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnet_ids
  ecs_security_group_id  = module.ecs.ecs_security_group_id
  allocated_storage      = var.rds_allocated_storage
  instance_class         = var.rds_instance_class
  engine_version         = var.rds_engine_version
  engine_version_major   = split(".", var.rds_engine_version)[0]
  master_username        = var.database_username
  master_password        = var.database_password
  multi_az               = var.rds_multi_az
  backup_retention_days  = var.rds_backup_retention_days
  enable_enhanced_monitoring = var.enable_enhanced_monitoring
  db_secret_arn          = module.secrets.db_secret_arn
  sns_topic_arn          = module.monitoring.sns_topic_arn
}

module "elasticache" {
  source = "./modules/elasticache"

  project_name           = var.project_name
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnet_ids
  ecs_security_group_id  = module.ecs.ecs_security_group_id
  node_type             = var.elasticache_node_type
  num_cache_nodes       = var.elasticache_num_cache_nodes
  engine_version        = var.elasticache_engine_version
  parameter_group_family = var.elasticache_parameter_group_family
  redis_auth_token      = var.jwt_secret
  sns_topic_arn         = module.monitoring.sns_topic_arn
  cloudwatch_log_group_name = aws_cloudwatch_log_group.redis.name
}

module "ecs" {
  source = "./modules/ecs"

  project_name           = var.project_name
  environment            = var.environment
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnet_ids
  alb_security_group_id  = module.alb.alb_security_group_id
  alb_target_group_arn   = module.alb.target_group_arn
  alb_listener_arn       = module.alb.listener_arn
  container_image        = var.container_image
  container_port         = var.container_port
  task_cpu               = var.ecs_task_cpu
  task_memory            = var.ecs_task_memory
  desired_count          = var.ecs_desired_count
  min_capacity           = var.ecs_min_capacity
  max_capacity           = var.ecs_max_capacity
  log_level              = var.environment == "prod" ? "WARNING" : "INFO"
  frontend_origins       = "https://yourdomain.com"
  api_workers            = 4
  rds_security_group_id  = module.rds.rds_security_group_id
  redis_security_group_id = module.elasticache.redis_security_group_id
  db_secret_arn          = module.secrets.db_secret_arn
  jwt_secret_arn         = module.secrets.jwt_secret_arn
  app_secret_arn         = module.secrets.app_secret_arn
  celery_secret_arn      = module.secrets.celery_secret_arn
  kms_key_arns           = [aws_kms_key.secrets.arn]
  db_proxy_endpoint      = module.rds.proxy_endpoint
  db_name                = "anpr"
  redis_endpoint         = module.elasticache.primary_endpoint
  redis_auth_token       = var.jwt_secret
  aws_region             = var.aws_region
  s3_bucket_frames       = module.s3.s3_bucket_frames_id
  s3_bucket_crops        = module.s3.s3_bucket_crops_id
  s3_bucket_audit        = module.s3.s3_bucket_audit_id
  log_retention_days     = var.log_retention_days
  otel_endpoint          = "http://localhost:4317"
}

resource "aws_acm_certificate" "main" {
  domain_name       = "anpr.yourdomain.com"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.project_name}-cert"
  }
}

resource "aws_kms_key" "secrets" {
  description             = "KMS key for ANPR Secrets Manager"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-secrets-key"
  }
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.project_name}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

resource "aws_cloudwatch_log_group" "redis" {
  name              = "/aws/elasticache/${var.project_name}/redis"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.project_name}-redis-logs"
  }
}

output "alb_dns_name" {
  value       = module.alb.alb_dns_name
  description = "DNS name of the load balancer"
}

output "rds_proxy_endpoint" {
  value = module.rds.proxy_endpoint
}

output "redis_endpoint" {
  value = module.elasticache.primary_endpoint
}

output "cloudwatch_dashboard" {
  value = module.monitoring.dashboard_url
}

output "s3_buckets" {
  value = {
    frames = module.s3.s3_bucket_frames_id
    crops  = module.s3.s3_bucket_crops_id
    audit  = module.s3.s3_bucket_audit_id
  }
}
