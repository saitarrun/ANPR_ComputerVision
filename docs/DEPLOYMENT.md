# ANPR Backend Deployment Strategy

## Overview

The ANPR backend uses **blue-green deployments** for production (zero downtime, instant rollback) and optional **canary deployments** (gradual rollout with automatic rollback on SLO breach). All infrastructure is managed with Terraform IaC.

### Deployment Environments

| Aspect | Dev | Stage | Prod |
|--------|-----|-------|------|
| **Infrastructure** | Single AZ, t3.micro | Multi-AZ, t3.medium (prod-sized) | Multi-AZ, t3.large + HA |
| **ECS Replicas** | 1 | 2 | 3+ |
| **Database** | Single-AZ | Single-AZ + backups | Multi-AZ, automated failover |
| **Redis** | Single node | Single node | Multi-AZ + cluster mode |
| **Backups** | None | Daily | Hourly + cross-region |
| **Approval** | Automatic | Automatic | Manual + on-call review |
| **Deployment** | On every merge | Blue-green (automated) | Blue-green (manual approval) |

### Key Metrics & SLOs

- **RTO (Recovery Time Objective):** <5 minutes (blue-green revert)
- **RPO (Recovery Point Objective):** <1 minute (database backups)
- **SLO:** 99.9% uptime (43min downtime/month)
- **Error Rate SLI:** <5% (alert at 5%+)
- **Latency SLI:** p99 <1 second (alert at 1s+)
- **Deployment Success Rate:** 100% (auto-rollback on failure)

---

## Part 1: Blue-Green Deployment Procedure

### What is Blue-Green?

Two identical production environments (blue = current, green = new). Deploy to green, run health checks, switch traffic. If issues, revert instantly.

**Advantages:**
- Zero-downtime deployments
- Instant rollback (1-2 seconds)
- Full environment testing before traffic switch
- Easy diagnosis of issues

**Disadvantages:**
- 2x infrastructure cost temporarily
- Requires stateless services (true for ANPR API)

### Step-by-Step Procedure

#### 1. Trigger Deployment

```bash
# Option A: Automatic on version tag (v1.0.0 → prod blue-green)
git tag v1.0.0
git push origin v1.0.0

# Option B: Manual dispatch
gh workflow run deploy.yml \
  -f environment=prod \
  -f deployment_strategy=blue-green
```

#### 2. Build & Test Phase (Automated)

The CI/CD pipeline automatically:
1. Lints code (Ruff)
2. Runs unit & integration tests
3. Performs security scanning (pip-audit, Trivy)
4. Builds Docker image and pushes to ECR with tag: `v1.0.0` or `prod-<commit-hash>`
5. Scans image for vulnerabilities

Check GitHub Actions for status: https://github.com/your-org/anpr/actions

#### 3. Stage Deployment (Automated)

The pipeline deploys to staging environment and runs:
- Smoke tests (API up, core endpoints 200)
- Integration tests (hit real DB, cache)
- Performance baseline tests (latency, throughput)

```bash
# Verify staging deployment manually
curl -s https://anpr-stage.example.com/healthz | jq .
```

#### 4. Manual Approval for Production

The GitHub Actions workflow pauses and requires explicit approval:

```bash
# In GitHub UI: Actions → Latest workflow → Review deployment

# Or via API:
gh api \
  --method POST \
  repos/your-org/anpr/actions/runs/WORKFLOW_RUN_ID/pending_deployments \
  -f environment_ids='["prod"]' \
  -f state=approved \
  -f comment="Approved for production"
```

#### 5. Determine Current Variant

```bash
# Check which variant is currently active
aws elbv2 describe-listeners \
  --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:loadbalancer/app/anpr-prod-alb/... \
  --query 'Listeners[0].DefaultActions[0].TargetGroupArn' \
  | grep -o -E 'blue|green'
# Output: blue (if blue is active, deploy to green)
```

#### 6. Deploy to New Variant (Green)

```bash
# Scale up green variant to 3 replicas
aws ecs update-service \
  --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-green \
  --desired-count 3 \
  --force-new-deployment \
  --region us-east-1

# Wait for healthy
aws ecs wait services-stable \
  --cluster anpr-prod-ecs-cluster \
  --services anpr-prod-ecs-service-green \
  --region us-east-1

# Expected: 3 tasks in RUNNING state, all passing health checks
aws ecs describe-services \
  --cluster anpr-prod-ecs-cluster \
  --services anpr-prod-ecs-service-green \
  --query 'services[0].{Running: runningCount, Desired: desiredCount, Status: status}' \
  --output table
```

#### 7. Validate New Variant

```bash
# Smoke tests (internal IP)
bash scripts/smoke_tests.sh http://green.anpr-prod.internal:8000

# Check logs for errors
aws logs tail /ecs/anpr/prod --filter-pattern "ERROR" --since 5m

# Verify database connectivity
curl -s http://green.anpr-prod.internal:8000/api/v1/regions | jq .

# Performance baseline
# (Optional) Run load test: ab -n 100 -c 10 http://green.anpr-prod.internal:8000/api/v1/regions
```

#### 8. Switch Traffic (ALB Update)

```bash
# Get green target group ARN
GREEN_TG=$(aws elbv2 describe-target-groups \
  --names anpr-prod-green \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

# Update listener to route traffic to green
aws elbv2 modify-listener \
  --listener-arn arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:listener/app/anpr-prod-alb/... \
  --default-actions Type=forward,TargetGroupArn=$GREEN_TG \
  --region us-east-1

echo "✅ Traffic switched to green at $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
```

#### 9. Monitor Deployment (30 minutes)

```bash
# Continuous monitoring script (runs in background)
bash scripts/monitor_deployment.sh \
  --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-green \
  --duration 30m \
  --error-threshold 5 \
  --latency-threshold 1000

# Manually check metrics (every 5 min)
watch -n 5 'bash scripts/check_metrics.sh'
```

**Metrics to watch:**
- Error rate: `errors / total_requests` (alert if >5%)
- P99 latency: (alert if >1s)
- CPU utilization: (alert if >80%)
- Database query latency: (alert if p99 >500ms)
- Celery queue depth: (alert if >1000 tasks)

**CloudWatch Dashboard:** https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=anpr-prod

#### 10. Complete Deployment (Scale Down Old Variant)

After 30 minutes of successful monitoring:

```bash
# Scale down blue (old variant) to 0
aws ecs update-service \
  --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-blue \
  --desired-count 0 \
  --region us-east-1

echo "✅ Deployment complete. Green is now production, blue is standby."
```

---

## Part 2: Canary Deployment Procedure (Optional)

### What is Canary?

Deploy new version alongside old. Route small percentage of traffic (5%) to new version, monitor metrics, gradually increase (5% → 25% → 50% → 100%). Auto-rollback if SLOs breach.

**When to use:**
- High-traffic services (>1000 RPS)
- High-risk changes (database migration, auth changes)
- Need to validate at scale before full rollout

**Comparison to Blue-Green:**

| Aspect | Blue-Green | Canary |
|--------|-----------|--------|
| Rollback Time | <2 sec | <5 min |
| Cost During Rollout | 2x | 1.1x |
| Issue Detection | At 100% traffic | At 5% traffic |
| Rollback Decision | Manual | Automatic |
| Deployment Duration | 30+ min | 30–60 min |

### Step-by-Step Canary Procedure

#### 1. Trigger Canary Deployment

```bash
gh workflow run deploy.yml \
  -f environment=prod \
  -f deployment_strategy=canary
```

#### 2. Scale Up Canary Service (1 replica, isolated)

```bash
# Deploy new version to separate ECS service (anpr-prod-ecs-canary)
aws ecs update-service \
  --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-canary \
  --desired-count 1 \
  --force-new-deployment \
  --region us-east-1

# Wait for healthy
aws ecs wait services-stable \
  --cluster anpr-prod-ecs-cluster \
  --services anpr-prod-ecs-canary
```

#### 3. Route 5% of Traffic to Canary

ALB weighted target groups:

```bash
# Create new listener rule: 95% → blue, 5% → canary
aws elbv2 create-listener-rule \
  --listener-arn arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:listener/app/anpr-prod-alb/... \
  --conditions Field=path-pattern,Values=/\* \
  --priority 1 \
  --actions \
    Type=forward,ForwardConfig='{
      TargetGroups=[
        {TargetGroupArn=<BLUE_TG>,Weight=95},
        {TargetGroupArn=<CANARY_TG>,Weight=5}
      ]
    }'
```

#### 4. Monitor at 5% (5 minutes)

```bash
# Watch error rate, latency, database queries
bash scripts/monitor_canary.sh \
  --service anpr-prod-ecs-canary \
  --weight 5 \
  --duration 5m \
  --error-threshold 10 \
  --latency-threshold 1500

# Check canary logs
aws logs tail /ecs/anpr/prod --filter-pattern "[ERROR, EXCEPTION, Traceback]" --since 5m
```

If metrics are good, continue. If SLOs breach, auto-rollback to blue.

#### 5. Increase to 25% Traffic

```bash
bash scripts/set_canary_weight.sh --weight 25
bash scripts/monitor_canary.sh --weight 25 --duration 5m
```

#### 6. Increase to 50% Traffic

```bash
bash scripts/set_canary_weight.sh --weight 50
bash scripts/monitor_canary.sh --weight 50 --duration 5m
```

#### 7. Full Rollout (100%)

```bash
bash scripts/set_canary_weight.sh --weight 100
```

#### 8. Cleanup (Remove Canary Service)

```bash
aws ecs update-service \
  --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-canary \
  --desired-count 0
```

---

## Part 3: Rollback Procedure

### Automatic Rollback (Triggered)

If error rate >5% or latency >1s during deployment, the monitoring script will exit with error:

```bash
# GitHub Actions catches the failure and runs the rollback job
aws elbv2 modify-listener \
  --listener-arn arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:listener/app/anpr-prod-alb/... \
  --default-actions Type=forward,TargetGroupArn=<PREVIOUS_TG> \
  --region us-east-1
```

**Time to recover:** <2 seconds (ALB traffic reroute)

### Manual Rollback (If Needed)

```bash
bash scripts/rollback_blue_green.sh prod

# Verify traffic is back on blue
curl https://anpr.example.com/healthz | jq .
```

### Database Rollback

If the new version introduced a database schema issue:

```bash
# SSH into RDS (via bastion)
psql postgresql://postgres:PASSWORD@anpr-prod-db.ACCOUNT.us-east-1.rds.amazonaws.com/anpr

# Run pre-tested rollback migration
\i /scripts/migrations/rollback_vX.Y.Z.sql

-- Verify schema
\d anpr_plates;
```

### What to Do After Rollback

1. **Document incident** in a GitHub issue with:
   - What went wrong (error message, metric breach)
   - When it happened (timestamp)
   - How it was detected
   - Rollback time and success

2. **Root cause analysis** (within 24 hours):
   - Review logs from failed variant
   - Identify the breaking change
   - Propose fix

3. **Prevention**:
   - Add test case for the scenario
   - Update staging validation
   - Consider additional smoke tests

4. **Re-deploy**:
   ```bash
   # Fix the issue, push to main, create new tag
   git tag v1.0.1
   git push origin v1.0.1
   # CI/CD pipeline will auto-deploy to prod again
   ```

---

## Part 4: Testing Before Deployment

### Smoke Tests (Pre-Deployment)

Runs automatically in GitHub Actions, but can run manually:

```bash
bash scripts/smoke_tests.sh https://anpr-stage.example.com

# Expected output:
# [INFO] Testing: Health check endpoint
# [INFO] ✓ Status code: 200 (expected 200)
# [INFO] ✓ Latency: 45ms (threshold: 1000ms)
# ...
# [INFO] All smoke tests passed!
```

### Integration Tests

```bash
# Run in staging (uses real DB, Redis)
uv run pytest tests/integration -q -m "not gpu"

# Expected: 50+ tests passing
```

### Load Test (Optional)

Before deploying a major change:

```bash
# Install Apache Bench
brew install httpd  # macOS

# Run 100 requests with concurrency 10
ab -n 100 -c 10 -H "Authorization: Bearer <token>" \
  https://anpr-stage.example.com/api/v1/regions

# Expected: <100ms latency, 0 failures
```

### Database Migration Validation

For changes involving DB schema:

```bash
# Test migration in staging
bash db/scripts/migrate_stage.sh

# Verify data integrity
aws rds describe-db-instances --db-instance-identifier anpr-stage-db \
  --query 'DBInstances[0].MasterUsername'

# Check table counts match
PROD_COUNT=$(psql -d prod-db -c "SELECT COUNT(*) FROM anpr_plates" -t)
STAGE_COUNT=$(psql -d stage-db -c "SELECT COUNT(*) FROM anpr_plates" -t)
echo "Prod: $PROD_COUNT | Stage: $STAGE_COUNT"
```

---

## Part 5: Monitoring Post-Deployment

### Dashboard Links

- **CloudWatch Metrics:** https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=anpr-prod
- **ECS Cluster:** https://console.aws.amazon.com/ecs/v2/clusters/anpr-prod-ecs-cluster
- **ALB Health:** https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#LoadBalancers:

### Key Metrics to Monitor (First 30 Minutes Post-Deploy)

```bash
# Error rate (5-minute window)
aws cloudwatch get-metric-statistics \
  --namespace ANPR/API \
  --metric-name ErrorRate \
  --statistics Average \
  --period 60 \
  --start-time "$(date -u -d '5 min ago' +'%Y-%m-%dT%H:%M:%S')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
  --output json | jq .Datapoints[].Average

# Latency p99 (5-minute window)
aws cloudwatch get-metric-statistics \
  --namespace ANPR/API \
  --metric-name RequestLatencyP99 \
  --statistics Average \
  --period 60 \
  --start-time "$(date -u -d '5 min ago' +'%Y-%m-%dT%H:%M:%S')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
  --output json | jq .Datapoints[].Average

# Celery queue depth
aws cloudwatch get-metric-statistics \
  --namespace ANPR/Workers \
  --metric-name QueueDepth \
  --statistics Average \
  --period 60 \
  --start-time "$(date -u -d '5 min ago' +'%Y-%m-%dT%H:%M:%S')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
  --output json | jq .Datapoints[].Average
```

### Alerting & On-Call

Alerts are configured to page the on-call engineer if:
- Error rate >5% for 2 minutes
- Latency p99 >1s for 5 minutes
- CPU >85% for 10 minutes
- Database latency p99 >500ms
- Celery queue depth >1000

---

## Part 6: Troubleshooting Common Issues

### Issue: Deployment Stuck (Tasks Won't Start)

**Symptoms:**
- ECS service shows 0 running tasks
- CloudWatch logs show CrashLoopBackOff

**Diagnosis:**
```bash
# Check task definition
aws ecs describe-task-definition \
  --task-definition anpr-api:1 \
  --query 'taskDefinition.containerDefinitions[0].environment' | jq .

# Check CloudWatch logs
aws logs tail /ecs/anpr/prod --since 10m

# Look for errors like:
# - Image not found (ECR permission issue)
# - Out of memory (increase task memory)
# - Database connection failed (check security groups)
```

**Resolution:**
- Verify ECR image exists: `aws ecr describe-images --repository-name anpr`
- Check task execution role has ECR pull permissions
- Verify RDS security group allows ECS tasks

### Issue: Health Checks Failing

**Symptoms:**
- Targets marked as "unhealthy" in ALB
- 503 Service Unavailable errors

**Diagnosis:**
```bash
# Check health check endpoint directly
curl -v http://ECS_TASK_IP:8000/healthz

# Check security group allows ALB → ECS traffic
aws ec2 describe-security-groups --group-ids sg-123abc \
  --query 'SecurityGroups[0].IgressRules'

# Check if application is running
aws ecs describe-tasks \
  --cluster anpr-prod-ecs-cluster \
  --tasks arn:aws:ecs:us-east-1:ACCOUNT:task/anpr-prod-ecs-cluster/abc123 \
  --query 'tasks[0].containers[0]'
```

**Resolution:**
- Verify health check endpoint is correctly implemented in code
- Check ALB security group allows port 8000 inbound
- Review application logs for startup errors

### Issue: Database Connection Failures During Deployment

**Symptoms:**
- Application logs show "could not connect to database"
- 500 errors on API endpoints

**Diagnosis:**
```bash
# Check RDS is accessible
aws rds describe-db-instances --db-instance-identifier anpr-prod-db \
  --query 'DBInstances[0].DBInstanceStatus'

# Test connection from ECS task security group
# (via bastion/SSH)
psql -h anpr-prod-db.ACCOUNT.us-east-1.rds.amazonaws.com -U postgres -d anpr

# Check security group rules
aws ec2 describe-security-groups --group-ids sg-rds \
  --query 'SecurityGroups[0].IgressRules' | grep 5432
```

**Resolution:**
- Verify RDS database is running (not being backed up)
- Check ECS task security group can reach RDS security group (port 5432)
- Verify database credentials in Secrets Manager

---

## Part 7: Deployment SLAs & Commitments

### Deployment SLAs

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Deployment Success Rate** | 100% | All deployments to prod succeed on first attempt |
| **MTTR (Mean Time to Recover)** | <5 min | Time from alert to traffic back on known-good version |
| **Deployment Duration** | <60 min | Time from approval to 100% traffic on new version |
| **Post-Deployment Monitoring** | 30 min | Continuous monitoring after traffic switch |
| **Rollback Time** | <2 sec | Time to revert traffic to previous variant |

### Error Budget

SLO: 99.9% uptime = 43 minutes downtime/month

- Blue-green deployment with issue: <2 min (rollback)
- Database migration failure: <5 min (rollback script)
- Unexpected scaling issue: <10 min (manual intervention)

---

## Part 8: Running Deployments Locally (Dev/Stage)

### Deploy to Dev (Local)

```bash
# Using docker-compose (hot reload)
docker-compose up api

# Deploy new changes
git push origin feature/my-feature
# Triggers auto-deploy to dev via GitHub Actions
```

### Deploy to Stage

```bash
# Stage auto-deploys on every merge to main
# Verify:
curl https://anpr-stage.example.com/healthz

# Manual re-deploy:
gh workflow run deploy.yml \
  -f environment=stage \
  -f deployment_strategy=blue-green
```

---

## Appendix: Command Reference

```bash
# Get current variant (blue or green)
aws elbv2 describe-listeners --listener-arn <LISTENER_ARN> \
  --query 'Listeners[0].DefaultActions[0].TargetGroupArn' | grep -oE 'blue|green'

# Get running task count
aws ecs describe-services --cluster anpr-prod-ecs-cluster \
  --services anpr-prod-ecs-service-green \
  --query 'services[0].{Running: runningCount, Desired: desiredCount}'

# Check recent logs
aws logs tail /ecs/anpr/prod --since 30m --follow

# See deployment events
aws ecs describe-services --cluster anpr-prod-ecs-cluster \
  --services anpr-prod-ecs-service-green \
  --query 'services[0].events[:5]'

# Force new deployment
aws ecs update-service --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-green \
  --force-new-deployment

# Scale service
aws ecs update-service --cluster anpr-prod-ecs-cluster \
  --service anpr-prod-ecs-service-green \
  --desired-count 5
```

---

**Last Updated:** 2026-05-28  
**Maintained by:** DevOps Team
