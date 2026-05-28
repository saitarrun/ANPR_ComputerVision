# ANPR Backend Deployment Strategy - Complete Documentation Index

## Overview

This directory contains comprehensive documentation for deploying and operating the ANPR backend on AWS. The deployment strategy emphasizes **zero-downtime updates** (blue-green), **instant rollback capability** (<2 seconds), and **full infrastructure automation** (Terraform IaC).

---

## Quick Navigation

### For Developers (New to Deployments)
1. Start here: **[QUICK_START_DEPLOY.md](QUICK_START_DEPLOY.md)** (5-minute read)
2. Before deploying: **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** (checklist)
3. Something went wrong: **[DEPLOYMENT.md#Part-6-Troubleshooting](DEPLOYMENT.md)** (troubleshooting)

### For DevOps Engineers
1. Architecture overview: **[DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md)** (20-minute read)
2. Step-by-step procedures: **[DEPLOYMENT.md](DEPLOYMENT.md)** (reference)
3. Emergency procedures: **[DEPLOYMENT.md#Part-3-Rollback-Procedure](DEPLOYMENT.md)** (immediate action)

### For Operations / On-Call
1. Incident response: **[DEPLOYMENT.md#Part-6-Troubleshooting](DEPLOYMENT.md)**
2. Post-deployment monitoring: **[DEPLOYMENT.md#Part-5-Monitoring](DEPLOYMENT.md)**
3. Health check commands: **[QUICK_START_DEPLOY.md#Checking-Deployment-Status](QUICK_START_DEPLOY.md)**

### For Infrastructure / Terraform
1. IaC structure: **[DEPLOYMENT_ARCHITECTURE.md#Infrastructure-as-Code](DEPLOYMENT_ARCHITECTURE.md)**
2. Terraform modules: `../terraform/modules/*/README.md` (per module docs)
3. Environment setup: `../terraform/environments/{dev,stage,prod}/terraform.tfvars`

---

## Documentation Files

### Core Deployment Guides

| File | Purpose | Audience | Length |
|------|---------|----------|--------|
| **[QUICK_START_DEPLOY.md](QUICK_START_DEPLOY.md)** | 60-second deploy guide + common issues | Developers, new users | 5 min |
| **[DEPLOYMENT.md](DEPLOYMENT.md)** | Complete blue-green & canary procedures + troubleshooting | DevOps, engineers | 60 min |
| **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** | Pre-deployment, deployment, and post-deployment checklists | Everyone before deploy | 10 min |
| **[DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md)** | High-level architecture, monitoring, disaster recovery | DevOps, architects | 30 min |
| **[INDEX.md](INDEX.md)** | This file — navigation guide | Everyone | 2 min |

### Implementation Files

| File | Purpose |
|------|---------|
| **[../.github/workflows/deploy.yml](../.github/workflows/deploy.yml)** | GitHub Actions CI/CD pipeline (fully automated) |
| **[../terraform/main.tf](../terraform/main.tf)** | Terraform root module orchestration |
| **[../terraform/modules/alb/](../terraform/modules/alb/)** | Load balancer module (blue-green target groups) |
| **[../terraform/modules/ecs/](../terraform/modules/ecs/)** | ECS cluster, services, task definitions |
| **[../terraform/modules/rds/](../terraform/modules/rds/)** | RDS PostgreSQL with Multi-AZ, backups |
| **[../terraform/modules/elasticache/](../terraform/modules/elasticache/)** | Redis cluster with failover |
| **[../scripts/smoke_tests.sh](../scripts/smoke_tests.sh)** | Health check validation script |
| **[../scripts/monitor_deployment.sh](../scripts/monitor_deployment.sh)** | Real-time deployment monitoring |
| **[../scripts/check_metrics.sh](../scripts/check_metrics.sh)** | CloudWatch metrics dashboard |
| **[../scripts/rollback_blue_green.sh](../scripts/rollback_blue_green.sh)** | Emergency rollback script |

---

## Deployment Flow (High-Level)

```
Developer pushes code
         │
         ├─ Create git tag: v1.0.0
         │  git tag v1.0.0 && git push origin v1.0.0
         │
         └─ GitHub Actions triggers deploy.yml
            │
            ├─ Build & Test (5-10 min)
            │  └─ Build Docker image, run tests, security scans
            │
            ├─ Deploy to Staging (5 min)
            │  └─ Run smoke tests, validation
            │
            ├─ Manual Approval (human gate)
            │  └─ Engineering team approves in GitHub UI
            │
            ├─ Deploy to Prod (Blue-Green, 30+ min)
            │  ├─ Scale up new variant (green)
            │  ├─ Validate health checks pass
            │  ├─ Switch ALB traffic to green (instant)
            │  ├─ Monitor for 30 minutes
            │  └─ Scale down old variant (blue)
            │
            └─ Monitoring (30+ minutes)
               └─ Alert on error rate >5%, latency >1s

If anything fails:
  → Automatic rollback to previous variant
  → Revert traffic in <2 seconds
  → Scale down failed variant
  → Notify team on Slack + PagerDuty
```

---

## Deployment Strategies

### Blue-Green (Production Recommended)

**Best for:** Production deployments, high-traffic services, need for instant rollback

```
Before:  Blue (active) ←─── ALB ←─── Users
         Green (standby)

Deploy:  Blue (active) ←─── ALB ←─── Users
         Green (starting)

After:   Blue (standby) ←─┐
         Green (active) ←─┴─── ALB ←─── Users

Rollback: Blue (active) ←─── ALB ←─── Users (instant, <2 sec)
          Green (failed)
```

**Advantages:**
- Zero downtime
- Instant rollback (<2 seconds)
- Full environment testing before traffic switch

**Procedure:** See [DEPLOYMENT.md#Part-1](DEPLOYMENT.md)

### Canary (Optional, High-Risk Changes)

**Best for:** Major changes, high-traffic services where you want to catch issues at scale

```
Step 1: Route 5% traffic to canary for 5 minutes
Step 2: If healthy, increase to 25% for 5 minutes
Step 3: If healthy, increase to 50% for 5 minutes
Step 4: If healthy, increase to 100%
Step 5: Remove canary service

Auto-rollback if error rate >10% or latency >1.5s
```

**Procedure:** See [DEPLOYMENT.md#Part-2](DEPLOYMENT.md)

---

## Key Metrics & SLOs

### Service Level Objectives (SLOs)

| Metric | Target | Alert Threshold | Recovery Time |
|--------|--------|-----------------|----------------|
| **Uptime** | 99.9% | <43min downtime/month | N/A |
| **Error Rate** | <1% | >5% × 2min | <5 min |
| **Latency P99** | <500ms | >1s × 5min | <5 min |
| **Deployment Success** | 100% | Any failure | Auto-rollback |
| **MTTR** | <5 min | Rollback + restart | <2 sec (blue-green) |

### Real-Time Monitoring

**CloudWatch Dashboard:** https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=anpr-prod

Monitored during deployment:
- Error rate (target: <1%)
- Latency p99 (target: <500ms)
- CPU utilization (target: <70%)
- Memory utilization (target: <70%)
- Database query latency (target: <100ms)
- Celery queue depth (target: <100 tasks)

---

## Common Scenarios

### Scenario 1: Deploy New Feature to Production

1. **Pre-deployment (24h before):**
   - [ ] All tests passing locally: `uv run pytest tests/ -q`
   - [ ] Code reviewed and approved
   - [ ] No security vulnerabilities: `uv run pip-audit`
   - [ ] Database migrations tested in staging
   - Checklist: [DEPLOYMENT_CHECKLIST.md#Pre-Deployment](DEPLOYMENT_CHECKLIST.md)

2. **Trigger deployment:**
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. **Monitor:**
   - GitHub Actions builds and tests (~5 min)
   - Deploy to staging (~5 min)
   - Waits for manual approval
   - You approve in GitHub UI
   - Deploys to prod blue-green (~30 min)
   - Monitors automatically for 30 min

4. **Verify:**
   - Open CloudWatch dashboard
   - Check error rate, latency
   - Monitor logs: `aws logs tail /ecs/anpr/prod --follow`

### Scenario 2: Emergency Rollback

1. **Detect issue:**
   - Error rate >5%
   - Latency spike >1s
   - Critical error in logs

2. **Rollback (automatic or manual):**
   ```bash
   bash scripts/rollback_blue_green.sh prod
   ```

3. **Verify:**
   - Check metrics return to normal
   - Confirm no errors in logs

4. **Investigate:**
   - Review logs from failed variant
   - Identify root cause
   - Create GitHub issue
   - Plan fix

### Scenario 3: Database Migration

1. **Test in staging first:**
   ```bash
   # Run migration in staging
   bash db/scripts/migrate_stage.sh

   # Verify data integrity
   ```

2. **Deploy with blue-green:**
   - Migration runs on blue variant first (before green)
   - If migration fails, blue rolls back automatically

3. **Validate:**
   - Check database schema: `\d anpr_plates`
   - Verify data counts match

### Scenario 4: Performance Degradation

1. **Check metrics:**
   ```bash
   bash scripts/check_metrics.sh

   # Watch for:
   # - CPU >85%
   # - Memory >85%
   # - Database latency >500ms
   ```

2. **Scale up (if needed):**
   ```bash
   aws ecs update-service --cluster anpr-prod-ecs-cluster \
     --service anpr-prod-ecs-service-green \
     --desired-count 5  # Increase from 3 to 5
   ```

3. **Investigate root cause:**
   - Check application logs
   - Analyze slow queries: `SELECT query, calls, mean_time FROM pg_stat_statements ORDER BY mean_time DESC`
   - Check Redis memory usage
   - Review recent code changes

---

## Critical Commands Reference

### Check Deployment Status
```bash
# Is deployment complete?
aws ecs describe-services --cluster anpr-prod-ecs-cluster \
  --services anpr-prod-ecs-service-green \
  --query 'services[0].{Running: runningCount, Desired: desiredCount, Status: status}'

# Current active variant (blue or green)?
aws elbv2 describe-listeners --listener-arn <LISTENER_ARN> \
  --query 'Listeners[0].DefaultActions[0].TargetGroupArn' | grep -o 'blue\|green'

# View recent logs
aws logs tail /ecs/anpr/prod --since 10m

# Check metrics
bash scripts/check_metrics.sh
```

### Emergency Rollback
```bash
# Instant rollback to previous variant
bash scripts/rollback_blue_green.sh prod

# Verify
curl https://anpr.example.com/healthz | jq .
```

### Manual Deployment (if automation fails)
```bash
# See [QUICK_START_DEPLOY.md#Manual-Deployment](QUICK_START_DEPLOY.md)
# or [DEPLOYMENT.md#Part-1](DEPLOYMENT.md) for step-by-step
```

---

## Troubleshooting Quick Reference

| Issue | Cause | Fix |
|-------|-------|-----|
| **"Tasks failing to start"** | App crash, image not found, mem OOM | Check logs: `aws logs tail /ecs/anpr/prod` |
| **"Health checks failing"** | App not responding on port 8000 | Test: `curl http://TASK_IP:8000/healthz` |
| **"Database connection errors"** | RDS unreachable, security group issue | Verify: `aws ec2 describe-security-groups` |
| **"Redis connection lost"** | Redis cluster down or timeout | Check: `redis-cli -h ENDPOINT ping` |
| **"Deployment hung/won't complete"** | ALB health checks stuck | Force: `aws ecs update-service --force-new-deployment` |

Full troubleshooting: [DEPLOYMENT.md#Part-6](DEPLOYMENT.md)

---

## Team Contacts

| Role | Slack | On-Call |
|------|-------|---------|
| **DevOps Lead** | @devops-lead | Primary (if infrastructure issue) |
| **Engineering Manager** | @manager | Secondary (escalation) |
| **On-Call Engineer** | PagerDuty | Rotation (alert on SLO breach) |

**On-Call Paging:**
- Error rate >5% × 2min → Page on-call
- Latency p99 >1s × 5min → Page on-call
- CPU >85% × 10min → Page ops

---

## Key SLAs & Commitments

| Aspect | SLA |
|--------|-----|
| **Deployment Success Rate** | 100% (auto-rollback on failure) |
| **Mean Time to Recover (MTTR)** | <5 minutes (blue-green revert <2 sec) |
| **Deployment Downtime** | 0 seconds (zero-downtime blue-green) |
| **Service Uptime** | 99.9% (43 minutes downtime/month allowed) |
| **Post-Deployment Monitoring** | 30 minutes continuous |
| **Rollback Time** | <2 seconds (ALB target group switch) |
| **Database Failover** | <2 minutes (RDS Multi-AZ automatic) |

---

## Next Steps

1. **New to deployments?** → Read [QUICK_START_DEPLOY.md](QUICK_START_DEPLOY.md)
2. **Planning a deployment?** → Follow [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)
3. **Deploying to production?** → Read [DEPLOYMENT.md#Part-1](DEPLOYMENT.md)
4. **Incident response?** → See [DEPLOYMENT.md#Part-6](DEPLOYMENT.md)
5. **Understanding architecture?** → Read [DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md)

---

## Document Maintenance

- **Last Updated:** 2026-05-28
- **Maintained by:** DevOps Team
- **Status:** Production-ready
- **Version:** 1.0.0

---

**Questions?** Reach out to @devops-lead on Slack or create an issue in GitHub.
