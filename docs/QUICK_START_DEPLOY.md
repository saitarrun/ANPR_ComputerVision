# Quick Start: Deploying ANPR Backend

## 60-Second Deploy (Automated)

```bash
# 1. Create a version tag
git tag v1.0.0
git push origin v1.0.0

# GitHub Actions automatically:
# - Builds Docker image
# - Runs tests and security scans
# - Deploys to staging
# - Waits for manual approval
# - Deploys to prod (blue-green)
# - Monitors for 30 minutes

# Check deployment status
gh workflow view deploy --repo your-org/anpr
```

---

## Manual Deployment (Step-by-Step)

### Pre-Flight (5 min)

```bash
# All tests passing?
uv run pytest tests/unit tests/integration -q

# Code linting?
uv run ruff check .

# Type checking?
uv run mypy anpr_core api ingest workers db
```

### Build & Push (10 min)

```bash
# Build Docker image locally (or let CI do it)
docker build -t anpr:v1.0.0 .

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/anpr:v1.0.0
```

### Deploy to Staging (5 min)

```bash
# Update ECS service to new image
aws ecs update-service \
  --cluster anpr-stage-ecs-cluster \
  --service anpr-stage-ecs-service-blue \
  --force-new-deployment \
  --region us-east-1

# Wait for healthy
aws ecs wait services-stable \
  --cluster anpr-stage-ecs-cluster \
  --services anpr-stage-ecs-service-blue

# Test
curl https://anpr-stage.example.com/healthz | jq .
```

### Deploy to Production (30 min)

```bash
# 1. Determine current active (blue or green)
ACTIVE=$(aws elbv2 describe-listeners \
  --listener-arn arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:listener/app/anpr-prod-alb/... \
  --query 'Listeners[0].DefaultActions[0].TargetGroupArn' \
  | grep -o -E 'blue|green')
NEW=$([[ $ACTIVE == "blue" ]] && echo "green" || echo "blue")

# 2. Scale up new variant
aws ecs update-service \
  --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-$NEW \
  --desired-count 3 \
  --force-new-deployment

# 3. Wait for healthy (2-3 min)
aws ecs wait services-stable \
  --cluster anpr-prod-ecs-cluster \
  --services anpr-prod-ecs-service-$NEW

# 4. Test new variant
bash scripts/smoke_tests.sh http://$NEW.anpr-prod.internal:8000

# 5. Switch traffic
aws elbv2 modify-listener \
  --listener-arn arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:listener/app/anpr-prod-alb/... \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:targetgroup/anpr-prod-$NEW/...

# 6. Monitor (30 min)
bash scripts/monitor_deployment.sh \
  --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-$NEW \
  --duration 30m

# 7. Scale down old variant
aws ecs update-service \
  --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-$ACTIVE \
  --desired-count 0
```

---

## Checking Deployment Status

### Real-Time Metrics

```bash
# Open CloudWatch dashboard (manual)
open "https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=anpr-prod"

# Or check via CLI
bash scripts/check_metrics.sh
```

### View Logs

```bash
# Last 5 minutes
aws logs tail /ecs/anpr/prod --since 5m

# Errors only
aws logs tail /ecs/anpr/prod --filter-pattern "ERROR" --since 30m

# Follow live
aws logs tail /ecs/anpr/prod --follow
```

### Task Status

```bash
# Running tasks
aws ecs list-tasks --cluster anpr-prod-ecs-cluster --service-name anpr-prod-ecs-service-green

# Task details
aws ecs describe-tasks \
  --cluster anpr-prod-ecs-cluster \
  --tasks <TASK_ARN> \
  --query 'tasks[0].{Status: lastStatus, CPU: cpu, Memory: memory}'
```

---

## Emergency Rollback (2 minutes)

```bash
# Switch ALB back to previous variant instantly
bash scripts/rollback_blue_green.sh prod

# Verify
curl https://anpr.example.com/healthz | jq .
```

---

## Database Rollback (If Schema Changed)

```bash
# SSH to RDS (via bastion)
ssh -i ~/.ssh/bastion.key ec2-user@bastion.example.com

# From bastion:
psql postgresql://postgres:PASSWORD@anpr-prod-db.ACCOUNT.us-east-1.rds.amazonaws.com/anpr

# Run rollback migration
\i /scripts/migrations/rollback_v1.0.0.sql

# Verify
\d anpr_plates;
```

---

## Common Issues

### "Tasks failing to start"

```bash
# Check logs
aws logs tail /ecs/anpr/prod --since 10m

# Common reasons:
# - Image not found: verify ECR repository has image
# - Out of memory: increase task memory in Terraform
# - Database connection failed: check security groups
# - Secrets not accessible: verify IAM role permissions
```

### "Health checks failing"

```bash
# Check if app is actually running
aws ecs describe-tasks --cluster anpr-prod-ecs-cluster --tasks <TASK_ARN> \
  --query 'tasks[0].containers[0]'

# Test health endpoint manually
curl http://TASK_IP:8000/healthz -v

# Check security group allows port 8000
aws ec2 describe-security-groups --group-ids sg-123abc \
  --query 'SecurityGroups[0].IgressRules'
```

### "Deployment hung / won't complete"

```bash
# Force new deployment
aws ecs update-service --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-green \
  --force-new-deployment

# Or scale to 0 and back up
aws ecs update-service --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-green \
  --desired-count 0

aws ecs update-service --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-green \
  --desired-count 3
```

---

## Useful Links

| Resource | Link |
|----------|------|
| **CloudWatch Dashboard** | https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=anpr-prod |
| **ECS Cluster** | https://console.aws.amazon.com/ecs/v2/clusters/anpr-prod-ecs-cluster |
| **RDS Database** | https://console.aws.amazon.com/rds/v2/instances/anpr-prod-db |
| **ALB** | https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#LoadBalancers: |
| **ECR Repository** | https://console.aws.amazon.com/ecr/repositories/anpr |
| **GitHub Actions** | https://github.com/your-org/anpr/actions |
| **Deployment Runbook** | `/docs/DEPLOYMENT.md` |
| **Deployment Checklist** | `/docs/DEPLOYMENT_CHECKLIST.md` |
| **Architecture** | `/docs/DEPLOYMENT_ARCHITECTURE.md` |

---

## Environment Variables

### ECS Task Environment (Set via Secrets Manager)

```
DATABASE_URL = postgresql+asyncpg://user:pass@db-proxy.region.rds.amazonaws.com:5432/anpr
REDIS_URL = redis://redis-primary.region.cache.amazonaws.com:6379/0
CELERY_BROKER_URL = redis://redis-primary.region.cache.amazonaws.com:6379/1
JWT_SECRET = <from-secrets-manager>
SECRET_KEY = <from-secrets-manager>
FERNET_KEY = <from-secrets-manager>
LOG_LEVEL = WARNING (prod) | INFO (stage) | DEBUG (dev)
WORKERS = 4
```

### ALB Health Check

```
Path: /healthz
Port: 8000
Interval: 30 seconds
Timeout: 10 seconds
Healthy Threshold: 2 consecutive successes
Unhealthy Threshold: 3 consecutive failures
```

---

## SLA Commitments

- **Deployment Success Rate:** 100%
- **MTTR (rollback time):** <2 minutes
- **Downtime:** 0 seconds (blue-green)
- **Post-deploy monitoring:** 30 minutes continuous
- **SLO (uptime):** 99.9% (43 min downtime/month)
- **Error rate alert:** >5% for 2+ minutes
- **Latency alert:** p99 >1s for 5+ minutes

---

## Key Team Contacts

| Role | Contact | On-Call |
|------|---------|---------|
| **DevOps Lead** | Slack: @devops-lead | Primary |
| **Engineering Manager** | Slack: @manager | Secondary |
| **On-Call Engineer** | PagerDuty: anpr-oncall | Rotation |

---

**Last Updated:** 2026-05-28
**Status:** Production-ready
