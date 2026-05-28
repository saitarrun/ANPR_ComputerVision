# ANPR Deployment Guide

Step-by-step walkthrough for deploying the ANPR backend to AWS.

## Phase 1: Pre-Deployment (1-2 hours)

### 1.1 Generate Secrets

```bash
# Create a secrets file locally (NEVER commit to git)
python3 << 'EOF'
import secrets
from cryptography.fernet import Fernet

db_password = secrets.token_urlsafe(32)  # 32+ chars, URL-safe
jwt_secret = Fernet.generate_key().decode()
app_secret = Fernet.generate_key().decode()
celery_key = Fernet.generate_key().decode()

print(f"""
# Secrets for prod deployment
export ANPR_DB_PASSWORD="{db_password}"
export ANPR_JWT_SECRET="{jwt_secret}"
export ANPR_APP_SECRET="{app_secret}"
export ANPR_CELERY_KEY="{celery_key}"
""")
EOF

# Save to secure location (1Password, vault, etc)
# DO NOT commit to git
```

### 1.2 Build & Push Docker Image

```bash
# Build image
docker build -t anpr:v1.0.0 .

# Tag for ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789.dkr.ecr.us-east-1.amazonaws.com

docker tag anpr:v1.0.0 \
  123456789.dkr.ecr.us-east-1.amazonaws.com/anpr:v1.0.0

# Push to ECR
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/anpr:v1.0.0

# Verify
aws ecr describe-images \
  --repository-name anpr \
  --image-ids imageTag=v1.0.0
```

### 1.3 Create ACM Certificate

```bash
# Request public certificate
aws acm request-certificate \
  --domain-name anpr.yourdomain.com \
  --subject-alternative-names "*.anpr.yourdomain.com" \
  --validation-method DNS \
  --region us-east-1

# Copy certificate ARN for later
# Validate DNS records (AWS console or via DNS provider)
```

### 1.4 Configure AWS CLI Credentials

```bash
aws configure

# Verify credentials work
aws sts get-caller-identity
```

## Phase 2: Infrastructure Deployment (30-45 min)

### 2.1 Initialize Terraform

```bash
cd terraform

# Option A: Remote state (recommended for prod)
aws s3 mb s3://anpr-state-prod-$(aws sts get-caller-identity --query Account --output text)

aws dynamodb create-table \
  --table-name anpr-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5

terraform init \
  -backend-config="bucket=anpr-state-prod-$(aws sts get-caller-identity --query Account --output text)" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=anpr-state-lock"

# Option B: Local state (dev only)
terraform init
```

### 2.2 Plan Deployment

```bash
# Validate configuration
terraform validate
terraform fmt -recursive

# Plan production deployment
terraform plan \
  -var-file="environments/prod/terraform.tfvars" \
  -var="database_username=anpr" \
  -var="database_password=${ANPR_DB_PASSWORD}" \
  -var="jwt_secret=${ANPR_JWT_SECRET}" \
  -var="secret_key=${ANPR_APP_SECRET}" \
  -var="celery_encryption_key=${ANPR_CELERY_KEY}" \
  -var="container_image=123456789.dkr.ecr.us-east-1.amazonaws.com/anpr:v1.0.0" \
  -out=anpr.tfplan

# Review plan output:
# + Create 50+ resources (VPC, subnets, security groups, RDS, Redis, ECS, ALB, etc)
# No resources should be deleted

# Count resources
terraform plan -json anpr.tfplan | jq '.resource_changes | length'
```

### 2.3 Apply Infrastructure

```bash
# Apply plan (takes ~15-20 min for RDS, Redis to fully initialize)
terraform apply anpr.tfplan

# Monitor progress
watch -n 5 'aws cloudformation describe-stacks \
  --stack-name anpr \
  --query "Stacks[0].StackStatus"'

# Or monitor specific resources
aws rds describe-db-instances \
  --db-instance-identifier anpr-db \
  --query "DBInstances[0].[DBInstanceStatus,Endpoint.Address]"

aws elasticache describe-replication-groups \
  --replication-group-id anpr-redis \
  --query "ReplicationGroups[0].Status"

aws ecs describe-services \
  --cluster anpr-cluster \
  --services anpr-service \
  --query "services[0].[runningCount,desiredCount,deployments]"
```

### 2.4 Verify Deployment

```bash
# Get outputs
terraform output

# Check RDS is accessible
ANPR_RDS_ENDPOINT=$(terraform output -raw rds_proxy_endpoint)
psql -h ${ANPR_RDS_ENDPOINT} \
  -U anpr \
  -d anpr \
  -c "SELECT version();"

# Check Redis is accessible
ANPR_REDIS_ENDPOINT=$(terraform output -raw redis_endpoint)
redis-cli -h ${ANPR_REDIS_ENDPOINT} \
  -a ${ANPR_JWT_SECRET} \
  ping

# Check S3 buckets
aws s3 ls | grep anpr

# Check ECS service is running
aws ecs list-services --cluster anpr-cluster

# Check ALB is healthy
ALB_DNS=$(terraform output -raw alb_dns_name)
curl -I https://${ALB_DNS}/health
```

## Phase 3: Domain & DNS Configuration (15 min)

### 3.1 Update DNS Records

```bash
# Get ALB DNS name
ALB_DNS=$(terraform output -raw alb_dns_name)

# Create CNAME record in your DNS provider
# anpr.yourdomain.com CNAME anpr-alb-xxxxx.us-east-1.elb.amazonaws.com

# Verify DNS propagation (may take 1-5 min)
nslookup anpr.yourdomain.com

# Update ACM certificate validation (if needed)
# AWS will send email or you can validate via DNS
```

### 3.2 Test HTTPS

```bash
# Wait for ACM certificate validation (2-5 min)
aws acm describe-certificate \
  --certificate-arn arn:aws:acm:us-east-1:123456789:certificate/xxxxx \
  --query "Certificate.DomainValidationOptions[0].ValidationStatus"

# Test HTTPS endpoint
curl -I https://anpr.yourdomain.com/health

# HTTP should redirect to HTTPS
curl -I http://anpr.yourdomain.com/health
# Expected: 301 Permanent Redirect to https://...
```

## Phase 4: Application Configuration (30 min)

### 4.1 Update FastAPI Environment Variables

The environment variables are already configured in ECS task definition via Terraform.
Verify via AWS console or CLI:

```bash
aws ecs describe-task-definition \
  --task-definition anpr:1 \
  --query "taskDefinition.containerDefinitions[0].environment[].[name,value]" \
  --output table
```

Key variables:
- `POSTGRES_HOST`: `anpr-proxy-xxxxx.rds.amazonaws.com` (RDS Proxy)
- `REDIS_URL`: `rediss://:TOKEN@anpr-redis-xxxxx.cache.amazonaws.com:6379/0`
- `S3_BUCKET_*`: Auto-populated from Terraform
- `OTEL_EXPORTER_OTLP_ENDPOINT`: Configure for observability (optional)

### 4.2 Run Database Migrations

```bash
# Exec into running ECS task
TASK_ID=$(aws ecs list-tasks --cluster anpr-cluster --service-name anpr-service \
  --query "taskArns[0]" --output text | awk -F'/' '{print $NF}')

aws ecs execute-command \
  --cluster anpr-cluster \
  --task ${TASK_ID} \
  --container anpr \
  --command "/bin/bash" \
  --interactive

# Inside container:
alembic upgrade head

# Verify schema
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"
```

### 4.3 Verify API Endpoints

```bash
# Health check
curl -s https://anpr.yourdomain.com/health | jq .

# Expected output:
# {
#   "status": "ok",
#   "version": "0.1.0",
#   "timestamp": "2026-05-28T10:00:00Z"
# }

# Login endpoint
curl -X POST https://anpr.yourdomain.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"initial_password"}'

# Create default user if needed
```

## Phase 5: Monitoring & Observability (15 min)

### 5.1 Configure CloudWatch Dashboards

```bash
# Open dashboard
DASHBOARD_URL=$(terraform output -raw cloudwatch_dashboard)
open "${DASHBOARD_URL}"

# Or via CLI
aws cloudwatch get-dashboard \
  --dashboard-name anpr-dashboard \
  | jq .
```

### 5.2 Test Alarms

```bash
# Verify SNS topic is subscribed
aws sns list-subscriptions-by-topic \
  --topic-arn $(terraform output -raw sns_topic_arn)

# Verify subscription (check email)
# Click confirmation link in SNS email

# Trigger test alarm
aws cloudwatch set-alarm-state \
  --alarm-name anpr-alb-unhealthy-hosts \
  --state-value ALARM \
  --state-reason "Testing"

# Verify you receive email alert
# Reset alarm
aws cloudwatch set-alarm-state \
  --alarm-name anpr-alb-unhealthy-hosts \
  --state-value OK \
  --state-reason "Test complete"
```

### 5.3 Enable X-Ray (Optional)

```bash
# Install X-Ray daemon in ECS
# Add to ECS task definition:
# - Container: xray-daemon, image: public.ecr.aws/xray/aws-xray-daemon:latest
# - Port: 2000 UDP

# Update FastAPI to use X-Ray
# Install: pip install aws-xray-sdk
# See documentation in code
```

## Phase 6: Load Testing (Optional)

### 6.1 Baseline Performance

```bash
# Install load testing tool
pip install locust

# Create locustfile.py
cat > locustfile.py << 'EOF'
from locust import HttpUser, task

class APIUser(HttpUser):
    @task
    def health(self):
        self.client.get("/health")

    @task
    def login(self):
        self.client.post("/auth/login", json={
            "username": "admin",
            "password": "password"
        })
EOF

# Run load test
locust -f locustfile.py \
  --host https://anpr.yourdomain.com \
  --users 100 \
  --spawn-rate 10 \
  --run-time 5m

# Monitor in CloudWatch during test
watch -n 5 'aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=anpr-service \
  --start-time $(date -u -d "5 min ago" +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 \
  --statistics Average'
```

### 6.2 Chaos Testing (Optional)

```bash
# Kill a task to verify auto-recovery
TASK_ID=$(aws ecs list-tasks --cluster anpr-cluster --service-name anpr-service \
  --query "taskArns[0]" --output text | awk -F'/' '{print $NF}')

aws ecs stop-task --cluster anpr-cluster --task ${TASK_ID}

# Observe:
# 1. CloudWatch shows 1 running task (from 3)
# 2. Auto-scaling policy triggers new task
# 3. ALB removes unhealthy target
# 4. Within 30sec, new task is running and healthy

# Verify recovery
watch -n 2 'aws ecs describe-services \
  --cluster anpr-cluster \
  --services anpr-service \
  --query "services[0].[runningCount,desiredCount]"'
```

## Phase 7: Documentation & Handoff (30 min)

### 7.1 Create Runbooks

Create operational runbooks for on-call:

```bash
cat > docs/RUNBOOK_HIGH_CPU.md << 'EOF'
# Runbook: High ECS CPU Alert

## Alert
- CloudWatch alarm: anpr-ecs-high-cpu
- Threshold: CPU > 70% for 3 min

## Investigation
1. Check current metrics
   ```
   aws cloudwatch get-metric-statistics \
     --namespace AWS/ECS \
     --metric-name CPUUtilization \
     --dimensions Name=ServiceName,Value=anpr-service \
     --start-time $(date -u -d "30 min ago" +%Y-%m-%dT%H:%M:%S) \
     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
     --period 60 \
     --statistics Average,Maximum
   ```

2. Check logs for errors
   ```
   aws logs tail /ecs/anpr --since 30m --follow
   ```

3. Check task count
   ```
   aws ecs describe-services \
     --cluster anpr-cluster \
     --services anpr-service \
     --query "services[0].[desiredCount,runningCount]"
   ```

## Remediation
- **Option A**: Auto-scaling should kick in (monitor for 5 min)
- **Option B**: Manually scale up
  ```
  aws ecs update-service \
    --cluster anpr-cluster \
    --service anpr-service \
    --desired-count 5
  ```
- **Option C**: Check if specific endpoint is slow (query logs)

## Prevention
- Review CloudWatch Insights for high-CPU queries
- Optimize slow endpoints
- Add caching if applicable
EOF
```

### 7.2 Update Architecture Diagram

```bash
# Create visual diagram in terraform/docs/architecture.md
# Include:
# - VPC layout with subnets
# - Security groups and rules
# - Data flow through ALB -> ECS -> RDS/Redis/S3
# - Monitoring and logging stack
```

### 7.3 Hand Off to Operations

Provide:
- [ ] Terraform code in git
- [ ] Runbooks for common incidents
- [ ] CloudWatch dashboard link
- [ ] Secrets stored securely (1Password, vault)
- [ ] On-call escalation process
- [ ] Cost optimization recommendations
- [ ] Disaster recovery procedure

## Post-Deployment Checklist

- [ ] All ECS tasks are running and healthy
- [ ] Database migrations completed
- [ ] HTTPS certificate is valid
- [ ] CloudWatch alarms are subscribed
- [ ] SNS email confirmed
- [ ] Load testing completed
- [ ] Documentation updated
- [ ] On-call runbooks created
- [ ] Backup/restore tested
- [ ] Cost monitoring enabled

## Rollback Plan

If deployment fails:

```bash
# Option 1: Destroy and redeploy
terraform destroy \
  -var-file="environments/prod/terraform.tfvars" \
  -auto-approve

# Option 2: Revert to previous ECS task definition
aws ecs update-service \
  --cluster anpr-cluster \
  --service anpr-service \
  --task-definition anpr:PREVIOUS_REVISION

# Option 3: Restore RDS from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier anpr-db-restored \
  --db-snapshot-identifier anpr-db-xxxxx
```

## Troubleshooting

### ECS Tasks Won't Start

```bash
# Check logs
aws logs tail /ecs/anpr --follow

# Common issues:
# - Container image doesn't exist in ECR
# - Database credentials are wrong
# - Redis auth token is invalid
# - Security group blocks database/Redis access
```

### Database Connection Refused

```bash
# Verify RDS Proxy is healthy
aws rds describe-db-proxy-targets \
  --db-proxy-name anpr-proxy \
  --query "Targets[*].HostInfo.HostStatus"

# Check security group
aws ec2 describe-security-groups \
  --group-ids sg-xxxxxxx \
  --query "SecurityGroups[0].IpPermissions"
```

### Redis Auth Failures

```bash
# Verify auth token in task definition
aws ecs describe-task-definition \
  --task-definition anpr:1 \
  | jq '.taskDefinition.containerDefinitions[0].environment[] | select(.name == "REDIS_URL")'

# Compare with Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id anpr/jwt
```

---

**Deployment completed!** Your ANPR backend is now running in production on AWS.
