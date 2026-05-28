# ANPR Backend Deployment Checklist

## Pre-Deployment (24 Hours Before)

### Code & Testing
- [ ] All tests passing locally and in CI/CD
- [ ] Code review completed (≥2 approvals)
- [ ] No security vulnerabilities flagged by Trivy, pip-audit
- [ ] Linting passes (Ruff, Mypy)
- [ ] Changelog updated with feature/fix descriptions
- [ ] CHANGELOG.md entries match the version being deployed

### Database
- [ ] Migration scripts tested in staging
- [ ] Rollback scripts prepared and tested
- [ ] Data validation queries prepared (before/after counts)
- [ ] Backup scheduled for deployment window
- [ ] RDS Multi-AZ enabled (prod)

### Infrastructure
- [ ] Terraform plan reviewed (terraform plan -var-file="prod.tfvars")
- [ ] Security groups allow ALB → ECS traffic
- [ ] RDS security group allows ECS → database traffic
- [ ] ACM certificate is valid (check expiration)

### Monitoring
- [ ] CloudWatch dashboards created/updated
- [ ] SNS topics configured for alerts
- [ ] PagerDuty integration active
- [ ] On-call engineer assigned
- [ ] Alert thresholds documented (error rate, latency, CPU, memory)

### Team Coordination
- [ ] Deployment window scheduled (off-peak hours)
- [ ] On-call engineer assigned
- [ ] Team notified (Slack announcement)
- [ ] Business stakeholders informed (ETA, expected impact)
- [ ] Rollback procedure reviewed with team

---

## Deployment Day (Blue-Green)

### 2 Hours Before Deployment

- [ ] Verify all team members are available
- [ ] Confirm no critical issues in production
- [ ] Check ECS cluster health: `aws ecs describe-clusters --clusters anpr-prod-ecs-cluster`
- [ ] Verify RDS backup completed: `aws rds describe-db-instances --db-instance-identifier anpr-prod-db`
- [ ] Check Celery worker queue is healthy: `celery -A workers.tasks inspect active_queues`
- [ ] Verify Redis connection: `redis-cli -h <redis-endpoint> ping`

### 30 Minutes Before Deployment

- [ ] Post deployment announcement to Slack: "Deploying ANPR v1.0.0 to production (blue-green). ETA: 30-40 minutes. Impact: None expected."
- [ ] Enable enhanced monitoring on dashboard
- [ ] Open CloudWatch dashboard in browser (keep visible during deployment)
- [ ] Prepare rollback runbook (print or have accessible)
- [ ] Notify on-call engineer deployment is about to start

### Deployment Initiation

- [ ] Create git tag: `git tag v1.0.0 && git push origin v1.0.0`
- [ ] Monitor GitHub Actions workflow: https://github.com/your-org/anpr/actions
- [ ] Verify build completes successfully (green checkmark)
- [ ] Verify security scanning passes (no critical vulnerabilities)

### Staging Deployment (Automated)

- [ ] Wait for deployment to staging (5-10 minutes)
- [ ] Check staging is healthy: `curl https://anpr-stage.example.com/healthz`
- [ ] Verify smoke tests pass (visible in GitHub Actions logs)
- [ ] Spot-check staging logs for errors: `aws logs tail /ecs/anpr/stage --since 5m`

### Manual Approval for Production

- [ ] Review deployment plan in GitHub Actions
- [ ] Approve production deployment (click "Approve and deploy")
- [ ] Document approval in incident tracking: who, when, why
- [ ] Confirm approval received (GitHub email notification)

### Blue-Green Switch (Green Deployment)

- [ ] Monitor green variant scaling up (3 tasks)
- [ ] Wait for green tasks to reach RUNNING state: `watch aws ecs describe-services --cluster anpr-prod-ecs-cluster --services anpr-prod-ecs-service-green`
- [ ] Verify all 3 green tasks pass health checks (2+ consecutive healthy checks)
- [ ] Run smoke tests on green: `bash scripts/smoke_tests.sh http://green.anpr-prod.internal:8000`
  - [ ] Health endpoint responds 200
  - [ ] Regions endpoint responds 200
  - [ ] Cameras endpoint responds 200
  - [ ] All latencies <1000ms
- [ ] Check green service logs for errors: `aws logs tail /ecs/anpr/prod --filter-pattern "ERROR" --since 5m`

### Traffic Switch

- [ ] Record current active variant (blue): `aws elbv2 describe-listeners --listener-arn <LISTENER_ARN> | grep TargetGroupArn`
- [ ] Switch ALB to green: Automated via GitHub Actions
- [ ] Verify traffic switched: `curl https://anpr.example.com/api/v1/regions` (should now hit green)
- [ ] Timestamp traffic switch: Record time in deployment log

### Post-Switch Monitoring (30 Minutes)

- [ ] Minute 0-5: Check error rate (target: <1%)
  - [ ] `aws cloudwatch get-metric-statistics --namespace ANPR/API --metric-name ErrorRate`
  - [ ] Check application logs for errors: `aws logs tail /ecs/anpr/prod --since 5m`
  - [ ] Verify database connections are stable: `SELECT count(*) FROM pg_stat_activity`
  
- [ ] Minute 5-10: Monitor latency (target: p99 <1s)
  - [ ] `aws cloudwatch get-metric-statistics --namespace ANPR/API --metric-name RequestLatencyP99`
  - [ ] Run manual latency test: `time curl https://anpr.example.com/api/v1/detections`
  
- [ ] Minute 10-15: Check resource utilization (target: CPU <70%, Memory <70%)
  - [ ] `bash scripts/check_metrics.sh`
  - [ ] Verify no OOMKilled tasks: `aws ecs describe-tasks --cluster anpr-prod-ecs-cluster`
  
- [ ] Minute 15-30: Verify end-to-end workflows
  - [ ] Create test detection: curl -X POST with JWT token
  - [ ] Retrieve detections: curl -X GET with JWT token
  - [ ] Verify database writes are working: SELECT count(*) FROM detections

- [ ] Minute 30: Final validation
  - [ ] All SLOs green (error rate <5%, latency p99 <1s)
  - [ ] No critical errors in logs
  - [ ] All 3 green tasks still RUNNING and healthy
  - [ ] Database connectivity confirmed
  - [ ] Celery workers processing normally

### Complete Deployment

- [ ] Scale down blue (old variant) to 0: Automated via GitHub Actions
- [ ] Record deployment completion time
- [ ] Post success message to Slack: "✅ ANPR v1.0.0 deployed to production. No issues detected. Blue-green deployment complete. Blue is now standby."
- [ ] Update deployment log in incident tracking

### Post-Deployment (Next 4 Hours)

- [ ] Monitor error rate every 15 minutes (first hour)
- [ ] Monitor latency p99 every 15 minutes (first hour)
- [ ] Check for any user-reported issues on Slack
- [ ] Verify background jobs are running normally (Celery)
- [ ] Check database query performance hasn't degraded
- [ ] Monitor disk usage on RDS (should be stable)

---

## Canary Deployment Checklist (Optional)

### Pre-Canary Validation (Same as Blue-Green)

- [ ] (All pre-deployment checks from blue-green apply)

### Canary Rollout

- [ ] Deploy canary service with 1 replica (isolated ECS task)
- [ ] Health checks pass (2+ consecutive successful)
- [ ] Route 5% of traffic to canary via weighted ALB target group
  - [ ] 95% → blue
  - [ ] 5% → canary
- [ ] Monitor canary for 5 minutes:
  - [ ] Error rate on canary <10% (alert threshold)
  - [ ] Latency p99 <1.5s (alert threshold)
  - [ ] CPU <80%, Memory <80%
- [ ] If issues detected, auto-rollback to 0% canary traffic

### Gradual Rollout (If Canary Healthy)

- [ ] Increase to 25% traffic (25% → canary, 75% → blue)
- [ ] Monitor for 5 minutes with same thresholds
- [ ] Increase to 50% traffic (50% → canary, 50% → blue)
- [ ] Monitor for 5 minutes
- [ ] Increase to 100% traffic (100% → canary)
- [ ] Remove canary service (scale to 0)

---

## Rollback Checklist (If Needed)

### Detection

- [ ] Error rate >5% for 2+ consecutive minutes
  - [ ] Revert ALB traffic to blue
  - [ ] Scale down green to 0
  - [ ] Document issue in GitHub issue
  
- [ ] Latency p99 >1s for 5+ consecutive minutes
  - [ ] Page on-call engineer
  - [ ] Assess whether issue is deployment-related or infrastructure
  - [ ] If deployment-related, initiate rollback
  
- [ ] Database error or corruption detected
  - [ ] Revert ALB traffic to blue immediately
  - [ ] Run database rollback script
  - [ ] Verify data integrity
  - [ ] Document incident

### Rollback Steps

- [ ] Get current active variant: `aws elbv2 describe-listeners --listener-arn <LISTENER_ARN>`
- [ ] Identify previous variant (blue if currently green)
- [ ] Run rollback script: `bash scripts/rollback_blue_green.sh prod`
- [ ] Verify traffic switched back: `curl https://anpr.example.com/healthz`
- [ ] Monitor for 5 minutes:
  - [ ] Error rate drops <5%
  - [ ] Latency p99 returns to <1s
  - [ ] No critical errors in logs
- [ ] Post rollback message to Slack with incident details
- [ ] Create incident post-mortem issue in GitHub

### Post-Rollback Investigation

- [ ] Collect logs from failed green variant: `aws logs get-log-events --log-group-name /ecs/anpr/prod --log-stream-name anpr-prod-ecs-service-green-*`
- [ ] Identify root cause
- [ ] Identify what tests missed this issue
- [ ] Plan fix and updated test cases
- [ ] Schedule re-deployment with fixes

---

## Testing & Validation

### Smoke Tests (Required)

```bash
bash scripts/smoke_tests.sh https://anpr.example.com

# Verify output:
# ✓ Health check endpoint: 200
# ✓ Latency: <1000ms
# ✓ List regions: 200
# ✓ List cameras: 200
# ✓ Auth required endpoint: 401
# ✓ Invalid endpoint: 404
```

### Integration Tests (Recommended)

```bash
uv run pytest tests/integration -q

# Expected: All tests passing
```

### Manual API Tests (Recommended)

```bash
# Get auth token
TOKEN=$(curl -X POST https://anpr.example.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@anpr.local","password":"password"}' | jq -r .access_token)

# List regions
curl -H "Authorization: Bearer $TOKEN" \
  https://anpr.example.com/api/v1/regions | jq .

# Create detection (test write)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plate":"ABC123","confidence":0.95}' \
  https://anpr.example.com/api/v1/detections | jq .
```

### Load Test (For High-Risk Deployments)

```bash
ab -n 100 -c 10 -H "Authorization: Bearer $TOKEN" \
  https://anpr.example.com/api/v1/regions

# Expected: <100ms latency, 0% failure rate
```

---

## Emergency Contacts

| Role | Name | Phone | Slack |
|------|------|-------|-------|
| On-Call Engineer | @on-call | (xxx) xxx-xxxx | #oncall |
| DevOps Lead | Name | (xxx) xxx-xxxx | @devops-lead |
| Engineering Manager | Name | (xxx) xxx-xxxx | @manager |
| CTO | Name | (xxx) xxx-xxxx | @cto |

---

## Post-Deployment Sign-Off

- [ ] All checks completed successfully
- [ ] No issues detected in first hour
- [ ] On-call engineer confirms stability
- [ ] Deployment documented in incident log
- [ ] Metrics baseline established for this version
- [ ] Engineering team notified of successful deployment

**Deployed by:** ________________  
**Date/Time:** ________________  
**Version:** ________________  
**Approval:** ________________  

---

## Quick Reference Commands

```bash
# Check deployment status
aws ecs describe-services --cluster anpr-prod-ecs-cluster --services anpr-prod-ecs-service-green

# Get logs from failed deployment
aws logs tail /ecs/anpr/prod --filter-pattern "ERROR" --since 30m

# Check which variant is active
aws elbv2 describe-listeners --listener-arn <LISTENER_ARN> | grep TargetGroupArn

# Manually switch traffic (emergency)
aws elbv2 modify-listener --listener-arn <LISTENER_ARN> \
  --default-actions Type=forward,TargetGroupArn=<BLUE_TG_ARN>

# Check task health
aws ecs describe-tasks --cluster anpr-prod-ecs-cluster --tasks <TASK_ARN>

# View recent events
aws ecs describe-services --cluster anpr-prod-ecs-cluster --services anpr-prod-ecs-service-green \
  --query 'services[0].events[:5]'
```

---

**Last Updated:** 2026-05-28  
**Created by:** DevOps Team
