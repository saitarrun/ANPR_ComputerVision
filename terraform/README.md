# ANPR Infrastructure-as-Code (Terraform)

Production-grade AWS infrastructure for the Automatic Number Plate Recognition (ANPR) system.

## Architecture Overview

```
Internet
   |
   v
[Route 53] -> [ALB: HTTPS/443]
                    |
                    v
              [ECS Fargate]
              (3 tasks, auto-scaling CPU/memory)
              /    |    \
             /     |     \
        [RDS]  [Redis]  [S3]
        Proxy  (HA)      (encrypted)
```

### Components

1. **VPC**: Public subnets for ALB, private subnets for compute/database, NAT gateway for outbound
2. **ECS Fargate**: Serverless container orchestration, auto-scaling based on CPU/memory
3. **RDS Proxy**: Connection pooling (reduces connection exhaustion from Celery workers)
4. **RDS PostgreSQL**: Multi-AZ, automated backups, encrypted
5. **ElastiCache Redis**: Primary + replica with automatic failover, encrypted auth
6. **S3**: Versioning, encryption (KMS), lifecycle policies, least-privilege access
7. **Secrets Manager**: Automatic secret rotation, encrypted with KMS
8. **ALB**: HTTPS-only (HTTP redirects), health checks, access logging to S3
9. **CloudWatch**: Logs aggregation, dashboards, alarms (SNS)
10. **IAM**: Least-privilege roles for ECS, RDS Proxy, Secrets Manager

## Prerequisites

- AWS CLI configured with credentials
- Terraform >= 1.5.0
- ACM certificate (or create via AWS Console)
- Docker image pushed to ECR

## Quick Start

### 1. Generate Secrets

```bash
# Generate strong secrets for your environment
python3 << 'EOF'
from cryptography.fernet import Fernet
import secrets

# Database password (16+ chars, mixed case, numbers, symbols)
db_pass = secrets.token_urlsafe(24)
print(f"DATABASE_PASSWORD={db_pass}")

# JWT secret
jwt = Fernet.generate_key().decode()
print(f"JWT_SECRET={jwt}")

# App secret
app_secret = Fernet.generate_key().decode()
print(f"SECRET_KEY={app_secret}")

# Celery encryption key
celery_key = Fernet.generate_key().decode()
print(f"CELERY_ENCRYPTION_KEY={celery_key}")
EOF
```

Store these securely (e.g., 1Password, AWS Secrets Manager).

### 2. Initialize Terraform

```bash
cd terraform

# Initialize with remote state backend (S3 + DynamoDB)
terraform init \
  -backend-config="bucket=anpr-state-prod" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=anpr-state-lock"

# Or use local state (dev only)
terraform init
```

### 3. Plan Deployment

```bash
# Development
terraform plan -var-file="environments/dev/terraform.tfvars" \
  -var="database_username=anpr" \
  -var="database_password=<STRONG_PASSWORD>" \
  -var="jwt_secret=<JWT_SECRET>" \
  -var="secret_key=<APP_SECRET>" \
  -var="celery_encryption_key=<CELERY_KEY>" \
  -var="container_image=<ECR_IMAGE_URI>"

# Production
terraform plan -var-file="environments/prod/terraform.tfvars" \
  -var="database_username=anpr" \
  -var="database_password=<STRONG_PASSWORD>" \
  ...
```

### 4. Apply Infrastructure

```bash
terraform apply -var-file="environments/dev/terraform.tfvars" \
  -var="database_username=anpr" \
  -var="database_password=<STRONG_PASSWORD>" \
  -var="jwt_secret=<JWT_SECRET>" \
  -var="secret_key=<APP_SECRET>" \
  -var="celery_encryption_key=<CELERY_KEY>" \
  -var="container_image=<ECR_IMAGE_URI>"
```

### 5. Retrieve Outputs

```bash
terraform output

# Key outputs:
# - alb_dns_name: Load balancer DNS (CNAME to your domain)
# - rds_proxy_endpoint: Database connection string
# - redis_endpoint: Redis connection string
# - cloudwatch_dashboard: Monitoring dashboard URL
# - s3_buckets: S3 bucket names
```

### 6. Configure Domain

```bash
# Point your domain's CNAME to ALB
# Example: anpr.yourdomain.com CNAME -> anpr-alb-xxxxxxxx.us-east-1.elb.amazonaws.com

# Update ACM certificate validation (DNS or email)
# Once validated, ALB will serve HTTPS
```

## Environment Variables (FastAPI)

Configure these in ECS task definition (already templated):

```bash
# From RDS Proxy
DATABASE_URL=postgresql+asyncpg://anpr:PASSWORD@anpr-proxy-xxx.rds.amazonaws.com:5432/anpr

# From ElastiCache Redis
REDIS_URL=rediss://:AUTH_TOKEN@anpr-redis-xxx.ng.0001.use1.cache.amazonaws.com:6379/0

# S3 buckets (created by Terraform)
S3_BUCKET_FRAMES=anpr-frames-123456789
S3_BUCKET_CROPS=anpr-crops-123456789
S3_BUCKET_AUDIT=anpr-audit-123456789

# From Secrets Manager (injected by ECS)
POSTGRES_USER=anpr
POSTGRES_PASSWORD=<from-secrets-manager>
JWT_SECRET=<from-secrets-manager>
SECRET_KEY=<from-secrets-manager>
CELERY_ENCRYPTION_KEY=<from-secrets-manager>
```

## Deployment Strategy

### Blue-Green Deployment (Zero-Downtime)

ECS service is configured for blue-green deployments:

```bash
# Update task definition
aws ecs update-service \
  --cluster anpr-cluster \
  --service anpr-service \
  --force-new-deployment

# ALB will:
# 1. Deploy new tasks (green)
# 2. Run health checks (must pass 2 consecutive checks)
# 3. Gradually shift traffic from blue to green
# 4. Rollback to blue if health checks fail

# Monitor deployment
watch -n 2 'aws ecs describe-services \
  --cluster anpr-cluster \
  --services anpr-service \
  --query "services[0].[runningCount,desiredCount,deployments]"'
```

### Rollback

```bash
# If deployment fails, ECS auto-rolls back via circuit breaker
# (configured in ecs/main.tf: deployment_circuit_breaker)

# Manual rollback to previous task definition
aws ecs update-service \
  --cluster anpr-cluster \
  --service anpr-service \
  --task-definition anpr:PREVIOUS_REVISION
```

## Scaling

### Horizontal (Add/Remove Tasks)

Auto-scaling is configured based on:
- **CPU**: Scale up if average CPU > 70% for 3 min
- **Memory**: Scale up if average memory > 80% for 3 min

```bash
# View current scaling activity
aws autoscaling describe-scaling-activities \
  --auto-scaling-group-name anpr-asg

# Manually adjust desired count (for quick scaling)
aws ecs update-service \
  --cluster anpr-cluster \
  --service anpr-service \
  --desired-count 5
```

### Vertical (Increase CPU/Memory per Task)

Update `ecs_task_cpu` and `ecs_task_memory` in tfvars, then:

```bash
terraform plan -var-file="environments/prod/terraform.tfvars" \
  -var="ecs_task_cpu=4096" \
  -var="ecs_task_memory=8192"
terraform apply
```

### Database (RDS)

Upgrade instance class with minimal downtime:

```bash
# Multi-AZ failover to replica (1-2 min downtime)
aws rds modify-db-instance \
  --db-instance-identifier anpr-db \
  --db-instance-class db.r6g.2xlarge \
  --apply-immediately

# Or schedule maintenance window
aws rds modify-db-instance \
  --db-instance-identifier anpr-db \
  --db-instance-class db.r6g.2xlarge \
  --preferred-maintenance-window "sun:04:00-sun:05:00"
```

### Redis (ElastiCache)

Automatic cluster mode resizing (no downtime with replica):

```bash
aws elasticache modify-replication-group \
  --replication-group-id anpr-redis \
  --cache-node-type cache.r6g.xlarge \
  --apply-immediately
```

## Monitoring & Alerts

### CloudWatch Dashboard

Open the dashboard URL from `terraform output`:

```
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=anpr-dashboard
```

Tracks:
- ECS: CPU, Memory, Task count
- RDS: CPU, Connections, Query latency
- Redis: CPU, Memory, Evictions
- ALB: Response time, 5xx errors, unhealthy targets
- S3: Bucket size, requests

### Alarms

All configured to alert via SNS email:

| Alarm | Threshold | Action |
|-------|-----------|--------|
| ECS CPU | >70% for 3 min | Scale up |
| ECS Memory | >80% for 3 min | Scale up |
| RDS CPU | >80% for 5 min | Page on-call |
| RDS Connections | >80 | Page on-call (capacity) |
| RDS Storage | <2 GB free | Page on-call |
| Redis CPU | >75% for 5 min | Page on-call |
| Redis Memory | >85% for 5 min | Page on-call |
| Redis Evictions | >100 in 5 min | Page on-call |
| ALB Response Time | >1s for 3 min | Page on-call |
| ALB 5xx Errors | >10 in 5 min | Page on-call |
| ALB Unhealthy Targets | >0 | Page on-call |

### Logs

All logs aggregated in CloudWatch:

```bash
# ECS application logs
aws logs tail /ecs/anpr --follow

# RDS slow queries
aws logs tail /aws/rds/instance/anpr-db/postgresql --follow

# Redis logs
aws logs tail /aws/elasticache/anpr/redis --follow

# ALB access logs
aws s3 ls s3://anpr-alb-logs-123456789/alb/
```

## Disaster Recovery

### RDS Backup & Restore

```bash
# Automated backups: every 6 hours, retained 30 days
aws rds describe-db-snapshots \
  --db-instance-identifier anpr-db \
  --query "DBSnapshots[*].[DBSnapshotIdentifier,SnapshotCreateTime]"

# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier anpr-db-restored \
  --db-snapshot-identifier anpr-db-xxxxx-xxxxx
```

### Redis Backup & Restore

```bash
# Manual snapshot
aws elasticache create-snapshot \
  --replication-group-id anpr-redis \
  --snapshot-name anpr-redis-backup-$(date +%s)

# Automatic snapshots: every 6 hours, retained 5 days
aws elasticache describe-snapshots \
  --query "Snapshots[?ReplicationGroupId=='anpr-redis']"

# Restore from snapshot
aws elasticache restore-from-cluster-snapshot \
  --replication-group-id anpr-redis-restored \
  --snapshot-name anpr-redis-xxxxx
```

### Full Infrastructure Rebuild (Disaster Recovery)

```bash
# 1. Re-run terraform apply (creates all infrastructure from code)
# 2. Restore RDS from latest snapshot
# 3. Restore Redis from latest snapshot
# 4. Deploy latest container image to ECS
# 5. Health checks validate everything is working

# RTO (Recovery Time Objective): <30 min
# RPO (Recovery Point Objective): <6 hours (snapshot interval)
```

## Cost Optimization

### Right-Sizing

Monitor utilization and adjust instance classes:

```bash
# View CPU/memory metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=anpr-service \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum

# If 95th percentile < 30%, downsize instance
```

### Spot Instances (Dev/Staging)

Update ECS capacity provider strategy to use Spot:

```hcl
# In ecs/main.tf
default_capacity_provider_strategy {
  weight            = 80
  capacity_provider = "FARGATE_SPOT"  # 70% cheaper
}

default_capacity_provider_strategy {
  weight            = 20
  capacity_provider = "FARGATE"       # On-demand backup
}
```

### Data Transfer

ElastiCache + RDS are in private subnets (no NAT charges). S3 uses VPC endpoint:

```hcl
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.us-east-1.s3"
  route_table_ids = [aws_route_table.private[*].id]
}
```

## Security Best Practices

### Network Security

- **VPC**: Private subnets for database, Redis, ECS
- **Security Groups**: Least-privilege ingress/egress
- **NACLs**: Block suspicious IPs (DDoS mitigation)
- **VPC Flow Logs**: Audit all traffic (stored in CloudWatch)

### Secrets Management

- **Secrets Manager**: DB password, JWT secret, API keys
- **Auto-Rotation**: Database password rotates every 30 days
- **KMS Encryption**: All secrets encrypted at rest with customer-managed KMS key
- **Audit Logging**: All secret access logged in CloudTrail

### Infrastructure Security

- **S3 Encryption**: All buckets encrypted with KMS
- **SSL/TLS**: ALB enforces HTTPS (HTTP redirects)
- **IAM Least-Privilege**: ECS tasks can only access their own buckets/secrets
- **DynamoDB State Lock**: Prevents concurrent Terraform runs
- **Backup Encryption**: RDS/Redis snapshots encrypted

### Compliance

- **Audit Trail**: All changes logged in CloudTrail + git
- **Access Logs**: ALB logs stored in S3 (immutable)
- **Data Retention**: Logs retained 30-90 days per environment
- **Encryption in Transit**: TLS 1.2+ enforced
- **Encryption at Rest**: All data encrypted with KMS

## Maintenance

### Regular Tasks

| Frequency | Task |
|-----------|------|
| Daily | Review CloudWatch alarms, logs |
| Weekly | Check database slow query logs, update security groups |
| Monthly | Review cost report, right-size instances, rotate secrets |
| Quarterly | Patch base images, test disaster recovery |
| Annually | Audit IAM policies, update security best practices |

### Updating Infrastructure

```bash
# 1. Update variable in terraform.tfvars or variables.tf
# 2. Run plan to review changes
terraform plan -var-file="environments/prod/terraform.tfvars" \
  -var="rds_instance_class=db.r6g.2xlarge"

# 3. Review output (shows [create], [modify], [destroy])
# 4. Apply when confident
terraform apply ...

# 5. Monitor deployments (RDS may require 5-10 min downtime)
# 6. Update git with new state
git add terraform.tfstate terraform.tfstate.backup
git commit -m "Update RDS instance class to r6g.2xlarge"
```

### Upgrading Terraform

```bash
# Check version compatibility
terraform version

# Upgrade to latest 1.5.x
brew install terraform  # or download from terraform.io

# Validate syntax after upgrade
terraform validate
terraform fmt -recursive

# No state migration needed for minor upgrades
```

## Troubleshooting

### ECS Tasks Failing to Start

```bash
# Check task definition
aws ecs describe-task-definition \
  --task-definition anpr:1 \
  --query "taskDefinition.[cpu,memory,containerDefinitions[*].name]"

# Check logs
aws logs tail /ecs/anpr --follow

# Check security groups allow database/Redis
aws ec2 describe-security-groups --filters "Name=group-name,Values=anpr-ecs-sg"

# Check container image exists in ECR
aws ecr describe-images --repository-name anpr
```

### Database Connection Timeouts

```bash
# Check RDS Proxy is working
aws rds describe-db-proxies --filters Name=DBProxyName,Values=anpr-proxy

# Check proxy target health
aws rds describe-db-proxy-targets \
  --db-proxy-name anpr-proxy \
  --query "Targets[*].[DBInstanceIdentifier,HostInfo.HostStatus]"

# Check security group allows ECS -> RDS
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxx \
  --protocol tcp \
  --port 5432 \
  --source-group sg-yyyyyyy
```

### Redis Connection Issues

```bash
# Test Redis connectivity from ECS task
aws ecs execute-command \
  --cluster anpr-cluster \
  --task <TASK_ID> \
  --container anpr \
  --command "/bin/bash" \
  --interactive

# Inside container:
redis-cli -h anpr-redis-xxx.ng.0001.use1.cache.amazonaws.com \
  -p 6379 -a $REDIS_AUTH_TOKEN ping
```

## Cleanup

```bash
# Destroy all infrastructure (WARNING: deletes databases)
terraform destroy -var-file="environments/dev/terraform.tfvars" \
  -var="database_username=anpr" \
  -var="database_password=xxxx" \
  -var="jwt_secret=xxxx" \
  -var="secret_key=xxxx" \
  -var="celery_encryption_key=xxxx" \
  -var="container_image=xxxx"

# Keep RDS snapshot (for recovery)
# S3 buckets are retained (enable versioning for safe deletion)
```

## Support & Documentation

- **Terraform Docs**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- **AWS Well-Architected**: https://aws.amazon.com/architecture/well-architected/
- **FastAPI + ECS**: https://fastapi.tiangolo.com/deployment/
- **PostgreSQL Best Practices**: https://www.postgresql.org/docs/current/
- **Redis on AWS**: https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/

## Questions?

Refer to the architecture diagram in `terraform/docs/architecture.md` or reach out to DevOps team.
