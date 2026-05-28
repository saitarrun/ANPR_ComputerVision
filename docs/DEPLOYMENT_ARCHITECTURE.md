# ANPR Backend Deployment Architecture

## Executive Summary

The ANPR backend is deployed using **blue-green deployments** for zero-downtime production updates and optional **canary deployments** for high-risk changes. All infrastructure is version-controlled in Terraform (IaC). The CI/CD pipeline is fully automated via GitHub Actions.

**Key Guarantees:**
- **RTO:** <5 minutes (blue-green revert)
- **RPO:** <1 minute (database backups)
- **Deployment SLO:** 99.9% success rate (auto-rollback on failure)
- **Downtime:** 0 seconds (blue-green is zero-downtime)

---

## Architecture Overview

### Infrastructure Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        Internet / Users                          │
│                    (HTTPS via ACM Certificate)                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Route 53 DNS   │ (anpr.example.com)
                    └────────┬────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  AWS VPC (10.0.0.0/16)                                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Public Subnets (AZ-a, AZ-b)                             │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │  Application Load Balancer (ALB)                │   │   │
│  │  │  - Blue Target Group (port 8000)                │   │   │
│  │  │  - Green Target Group (port 8000)               │   │   │
│  │  │  - HTTPS Listener (port 443)                    │   │   │
│  │  │  - HTTP Listener → HTTPS Redirect               │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────┘   │
│                             │                                      │
│  ┌──────────────────────────┴──────────────────────────┐         │
│  │          Private Subnets (AZ-a, AZ-b, AZ-c)        │         │
│  │                                                     │         │
│  │  ┌────────────────────────┬────────────────────┐  │         │
│  │  │   ECS Fargate Cluster  │                    │  │         │
│  │  │ ┌──────────────────┐   │ ┌──────────────┐   │  │         │
│  │  │ │ Blue Service     │   │ │ Green Service│   │  │         │
│  │  │ │ (3 tasks)        │   │ │ (0-3 tasks)  │   │  │         │
│  │  │ │ - anpr-api       │   │ │ - anpr-api   │   │  │         │
│  │  │ │ - Celery workers │   │ │ - Celery...  │   │  │         │
│  │  │ └──────────────────┘   │ └──────────────┘   │  │         │
│  │  └────────────────────────┴────────────────────┘  │         │
│  │                                                     │         │
│  │  ┌──────────────────────────────────────────────┐  │         │
│  │  │       RDS PostgreSQL (Multi-AZ)              │  │         │
│  │  │  - Primary (AZ-a)                            │  │         │
│  │  │  - Standby Replica (AZ-b)                    │  │         │
│  │  │  - Automated backups (hourly)                │  │         │
│  │  │  - Connection proxy (RDS Proxy)              │  │         │
│  │  └──────────────────────────────────────────────┘  │         │
│  │                                                     │         │
│  │  ┌──────────────────────────────────────────────┐  │         │
│  │  │     ElastiCache Redis (Multi-AZ)             │  │         │
│  │  │  - Primary node (AZ-a)                       │  │         │
│  │  │  - Replica node (AZ-b)                       │  │         │
│  │  │  - Encryption in transit & at-rest           │  │         │
│  │  │  - Automatic failover enabled                │  │         │
│  │  └──────────────────────────────────────────────┘  │         │
│  │                                                     │         │
│  │  ┌──────────────────────────────────────────────┐  │         │
│  │  │            S3 Data Storage                    │  │         │
│  │  │  - Frames bucket (versioned, encrypted)      │  │         │
│  │  │  - Crops bucket (versioned, encrypted)       │  │         │
│  │  │  - Audit bucket (immutable, encrypted)       │  │         │
│  │  └──────────────────────────────────────────────┘  │         │
│  │                                                     │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │            AWS Secrets Manager                           │    │
│  │  - Database credentials (rotated 90-day)                │    │
│  │  - JWT secret key                                       │    │
│  │  - Encryption key (KMS)                                 │    │
│  │  - Celery auth token                                    │    │
│  └──────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  CloudWatch (Monitoring & Observability)                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Dashboards:                                             │   │
│  │  - Deployment dashboard (error rate, latency, CPU)       │   │
│  │  - ECS service health (running tasks, restarts)          │   │
│  │  - Database metrics (connections, queries, latency)      │   │
│  │  - Redis metrics (keys, memory, evictions)               │   │
│  │  - ALB metrics (request count, response time, 5xx)       │   │
│  │                                                          │   │
│  │  Alarms (via SNS → PagerDuty):                           │   │
│  │  - Error rate >5% for 2min                               │   │
│  │  - Latency p99 >1s for 5min                              │   │
│  │  - CPU >85% for 10min                                    │   │
│  │  - Memory >85% for 10min                                 │   │
│  │  - DB connections exhausted                              │   │
│  │  - Unhealthy targets behind ALB                          │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

---

## Blue-Green Deployment Flow

### Deployment Timeline

```
T+0min    ┌─ Trigger deployment via git tag
          │  git tag v1.0.0 && git push origin v1.0.0
          │
T+1-5min  ├─ Build & Test Phase (CI/CD)
          │  - Build Docker image
          │  - Run linting, unit tests, integration tests
          │  - Security scanning (Trivy, pip-audit)
          │  - Push to ECR
          │
T+5-10min ├─ Deploy to Staging (Automated)
          │  - Scale up staging service
          │  - Run smoke tests
          │  - Verify metrics
          │
T+10min   ├─ Manual Approval (Human Gate)
          │  - Review GitHub Actions summary
          │  - Approve production deployment
          │
T+10-15min├─ Scale Up Green (New Variant)
          │  - Deploy green service: 0 → 3 replicas
          │  - Wait for healthy (ECS task health checks)
          │
T+15-20min├─ Validate Green
          │  - Smoke tests pass (API responds 200)
          │  - Check logs for errors
          │  - Verify database connectivity
          │
T+20-25min├─ Switch Traffic (ALB Update)
          │  - Update ALB listener rule
          │  - Point default action to green target group
          │  - Traffic flows to green (INSTANT)
          │
T+25min   ├─ Monitor Green (30 minutes continuous)
          │  - Check error rate (target: <1%)
          │  - Check latency p99 (target: <1s)
          │  - Check CPU, memory (target: <70%)
          │  - Monitor database queries
          │  - Check Celery queue depth
          │
T+55min   ├─ Scale Down Blue (Old Variant)
          │  - Scale blue: 3 → 0 replicas
          │  - Blue remains available as fallback
          │
T+60min   └─ Deployment Complete ✅
             - Update deployment log
             - Notify team on Slack
             - Establish new metrics baseline
```

### State Transitions

```
Pre-Deployment:
  Blue (running, active traffic) ↔ Green (not running, no traffic)

During Deployment:
  Blue (running, active)  →  Green (starting)
  [Health checks on green]
  Blue (running, active)  →  Green (running, healthy)
  [Switch ALB target group]
  Blue (running, standby) ←  Green (running, active)
  [Monitor for 30 minutes]
  Blue (stopped, standby) ←  Green (running, active)

Deployment Success:
  Green is production, Blue is standby

Rollback (If Needed):
  Blue (running, standby) →  Green (running, unhealthy)
  [ALB reverts to blue target group]
  Blue (running, active)  ←  Green (stops)

Post-Rollback:
  Blue is production, Green is stopped (for investigation)
```

---

## CI/CD Pipeline

### GitHub Actions Workflow

```
github event (push tag or manual dispatch)
         │
         ├─ prepare (determine env, image tag)
         │
         ├─ parallel: lint, test, security
         │
         ├─ build (build Docker image, push to ECR)
         │
         ├─ scan-image (Trivy vulnerability scan)
         │
         ├─ deploy-stage (ECS update, smoke tests)
         │
         ├─ approval (manual gate for prod) [IF prod]
         │
         ├─ deploy-prod-blue-green [IF prod & approved]
         │  ├─ Determine current active variant (blue/green)
         │  ├─ Scale up new variant to 3 replicas
         │  ├─ Wait for healthy (ECS service stable)
         │  ├─ Run smoke tests on new variant
         │  ├─ Switch ALB traffic to new variant
         │  ├─ Monitor for 30 minutes (error rate, latency, CPU)
         │  ├─ If SLO breach: auto-rollback (exit with error)
         │  └─ Scale down old variant
         │
         └─ rollback (if deploy-prod-blue-green fails)
            ├─ Identify previous variant
            ├─ Switch ALB back to previous variant
            ├─ Scale down failed variant
            └─ Notify team on Slack
```

### Deployment Status

| Stage | Status Indicator | Expected Time | Success Criteria |
|-------|------------------|----------------|-----------------|
| Build | ✅ Green check | 5 min | Docker image pushed to ECR, signed |
| Test | ✅ All tests pass | 5 min | Unit, integration, and smoke tests pass |
| Security | ✅ No critical vulns | 2 min | Trivy scan complete, no critical findings |
| Stage Deploy | ✅ Service healthy | 5 min | 2+ tasks running, health checks pass |
| Stage Tests | ✅ Smoke tests pass | 3 min | Health, regions, cameras endpoints 200 |
| Approval | ⏳ Waiting | Manual | Engineering team approves |
| Blue-Green Deploy | ✅ Traffic switched | 40 min | Green running, traffic switched, 30min monitored |
| Monitoring | ✅ SLOs green | Continuous | Error rate <5%, latency <1s, CPU <70% |
| Cleanup | ✅ Blue scaled down | After 30min | Old variant stopped, logged |

---

## Monitoring & Observability

### Key Metrics Dashboard

**URL:** https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=anpr-prod

| Metric | Target | Alert Threshold | Dashboard |
|--------|--------|-----------------|-----------|
| **Error Rate** | <1% | >5% for 2min | ANPR/API namespace |
| **Latency P99** | <500ms | >1s for 5min | ANPR/API namespace |
| **Latency P50** | <100ms | >300ms | ANPR/API namespace |
| **Request Rate** | Baseline | Spike >50% | AWS/ApplicationELB |
| **CPU Utilization** | 40-60% | >85% for 10min | AWS/ECS |
| **Memory Utilization** | 50-70% | >85% for 10min | AWS/ECS |
| **DB Connections** | <50 | >100 | AWS/RDS |
| **DB Query Latency P99** | <100ms | >500ms | AWS/RDS |
| **Celery Queue Depth** | <100 | >1000 | ANPR/Workers |
| **Task Restart Count** | 0 | >1 | AWS/ECS |
| **Target Health** | All healthy | Any unhealthy | AWS/ApplicationELB |

### CloudWatch Alarms

All alarms route to SNS topic → PagerDuty for on-call notification:

| Alarm | Trigger | Action |
|-------|---------|--------|
| HighErrorRate | Error rate >5% × 2min | Page on-call, auto-rollback if within 5min of deploy |
| HighLatency | P99 latency >1s × 5min | Page on-call, investigate database |
| HighCPU | CPU >85% × 10min | Page ops, may scale up or investigate |
| HighMemory | Memory >85% × 10min | Page ops, investigate memory leak or OOM killer |
| UnhealthyTargets | Any target unhealthy × 2min | Page on-call, check logs for crash loop |
| DatabaseConnectionExhausted | Connections >100 | Page on-call, check for connection leak |
| CeleryQueueBacklog | Queue depth >1000 × 5min | Page ops, add more workers |
| CertificateExpiring | <30 days to expiration | Email ops team daily |

---

## Disaster Recovery & Failover

### RTO/RPO Targets

| Scenario | RTO | RPO | Method |
|----------|-----|-----|--------|
| **ECS Task Crash** | <1 min | None (stateless) | Auto-restart via ECS |
| **ALB Unhealthy Targets** | <2 min | None | ECS health check, restart |
| **Database Connection Lost** | <5 min | <1 min | RDS Proxy, retry logic |
| **Redis Connection Lost** | <1 min | Cache loss only | Auto-reconnect, warm cache |
| **ECS Service Degradation** | <5 min | None (blue-green) | Manual or auto-rollback |
| **RDS Primary Failure** | <2 min | <1 min | Automatic failover to standby (Multi-AZ) |
| **Entire Availability Zone Down** | <10 min | <1 min | RDS Multi-AZ, cross-AZ ECS |
| **Data Corruption** | <30 min | <1 hour | RDS restore from backup |

### Backup Strategy

| Resource | Frequency | Retention | Recovery |
|----------|-----------|-----------|----------|
| **RDS Database** | Hourly snapshots | 30 days | `aws rds restore-db-instance-from-db-snapshot` (5 min) |
| **RDS Transaction Logs** | Continuous | 7 days | Point-in-time recovery (PITR) |
| **S3 Data** | Versioning enabled | Indefinite | Restore previous version |
| **Configuration** | Git commits | Indefinite | Terraform apply (5 min) |
| **Secrets** | Secrets Manager backup | Automatic | Restore from AWS backup |

### Failover Procedure

```
Detect Failure:
  CloudWatch alarm: UnhealthyTargets
  Error rate: >5% for 2 minutes

Automatic Actions (ECS):
  1. Mark target unhealthy
  2. ECS detects failed task
  3. Terminate failed task
  4. Launch replacement task (Desired=3)
  5. Wait for healthy (health checks pass 2x)
  6. Traffic routed to healthy targets

Manual Actions (If Needed):
  1. Check CloudWatch logs: /ecs/anpr/prod
  2. Verify RDS is reachable
  3. Check Redis connection
  4. Force new deployment: aws ecs update-service --force-new-deployment
  5. Monitor metrics for 30 minutes

If Deployment Fails:
  1. Trigger automatic rollback script
  2. Switch ALB to previous variant (blue)
  3. Scale down failed variant (green)
  4. Investigate root cause
  5. Prepare fix, re-deploy

If RDS Primary Fails:
  1. RDS Multi-AZ automatic failover (2 min)
  2. Standby becomes new primary
  3. Update RDS endpoint in Secrets Manager (done by RDS)
  4. ECS tasks retry connections automatically
  5. Monitor database metrics for 30 minutes

If Entire AZ Down:
  1. RDS multi-AZ failover
  2. ECS auto-places tasks in other AZs
  3. Route 53 DNS resolves to healthy targets
  4. Application continues serving
```

---

## Security Architecture

### Secrets Management

All credentials stored in AWS Secrets Manager with encryption (KMS):

```
RDS Master Password
├─ Stored: AWS Secrets Manager
├─ Rotation: Every 90 days (Lambda)
├─ Access: ECS task role (IRSA)
└─ Usage: DATABASE_URL in ECS task

JWT Secret Key
├─ Stored: AWS Secrets Manager
├─ Rotation: Annual (manual)
├─ Access: ECS task role (IRSA)
└─ Usage: Token signing/verification

Fernet Encryption Key
├─ Stored: AWS Secrets Manager
├─ Rotation: Annual (manual)
├─ Access: ECS task role (IRSA)
└─ Usage: Application secret encryption

Redis AUTH Token
├─ Stored: AWS Secrets Manager
├─ Rotation: Annual (manual)
├─ Access: ECS task role (IRSA)
└─ Usage: Redis authentication
```

### Network Security

```
Ingress:
  Internet → Route 53 (DNS)
  Route 53 → ALB (HTTPS port 443, HTTP port 80→443)
  ALB → ECS Tasks (port 8000)

Egress from ECS:
  ECS → RDS (port 5432) [Security group rule: RDS SG allow from ECS SG]
  ECS → Redis (port 6379) [Security group rule: Redis SG allow from ECS SG]
  ECS → S3 (HTTPS, IAM role allow)
  ECS → Secrets Manager (HTTPS, IAM role allow)
  ECS → CloudWatch Logs (HTTPS, IAM role allow)

Outbound Internet:
  ECS → Internet (HTTP/HTTPS for external APIs) [NAT Gateway in public subnet]
```

### IAM Least-Privilege

```
ECS Task Role (IRSA):
  - ReadWrite: S3 buckets (frames, crops)
  - ReadWrite: DynamoDB (if used for caching)
  - Read: Secrets Manager (DB, JWT, encryption keys)
  - Write: CloudWatch Logs
  - Write: CloudWatch Metrics (custom metrics)

ECR Push (GitHub Actions):
  - PutImage: ECR repository
  - DescribeRepositories: Verify ECR exists

Terraform Role:
  - Full access to: VPC, RDS, Redis, ECS, ALB, S3, Secrets Manager, CloudWatch
  - Read-only: CloudTrail for audit
```

---

## Deployment Checklists & Runbooks

- **Pre-Deployment:** `/docs/DEPLOYMENT_CHECKLIST.md` → "Pre-Deployment" section
- **Blue-Green Procedure:** `/docs/DEPLOYMENT.md` → "Part 1"
- **Canary Procedure:** `/docs/DEPLOYMENT.md` → "Part 2"
- **Rollback Procedure:** `/docs/DEPLOYMENT.md` → "Part 3"
- **Troubleshooting:** `/docs/DEPLOYMENT.md` → "Part 6"

---

## Infrastructure as Code (Terraform)

### Directory Structure

```
terraform/
├── main.tf                 # Root module orchestration
├── variables.tf            # Input variables (environment-specific)
├── versions.tf             # Terraform version constraints
│
├── environments/
│   ├── dev/
│   │   ├── terraform.tfvars    # Dev-specific values (1 ECS task, t3.micro DB)
│   │   └── backend.tf          # S3 state backend
│   ├── stage/
│   │   ├── terraform.tfvars    # Stage-specific values (prod-sized)
│   │   └── backend.tf
│   └── prod/
│       ├── terraform.tfvars    # Prod-specific values (HA, Multi-AZ)
│       └── backend.tf
│
└── modules/
    ├── vpc/                # VPC, subnets, NAT, security groups
    ├── alb/                # Load balancer, target groups (blue/green)
    ├── ecs/                # ECS cluster, task definitions, services
    ├── rds/                # RDS PostgreSQL, Multi-AZ, backups
    ├── elasticache/        # Redis cluster, failover, encryption
    ├── s3/                 # S3 buckets, versioning, encryption
    ├── secrets/            # Secrets Manager, rotation
    ├── monitoring/         # CloudWatch dashboards, alarms
    └── audit/              # CloudTrail, audit logging
```

### Deploying Infrastructure

```bash
# Initialize Terraform (first time only)
cd terraform/environments/prod
terraform init -backend-config="bucket=anpr-state-prod" \
  -backend-config="key=prod.tfstate" \
  -backend-config="region=us-east-1"

# Validate configuration
terraform validate

# Plan changes
terraform plan -var-file="terraform.tfvars"

# Apply (with approval)
terraform apply -var-file="terraform.tfvars"

# Destroy (careful in prod!)
terraform destroy -var-file="terraform.tfvars"
```

---

## Cost Estimation

### Monthly Resource Costs (Production)

| Resource | Size | Quantity | Cost/Month |
|----------|------|----------|-----------|
| **ALB** | 1 | - | $16 |
| **ECS Fargate Tasks** | 1024 CPU, 2048 GB RAM | 3 active + 3 standby | $450 |
| **RDS PostgreSQL** | t4g.large | 1 primary + 1 standby (Multi-AZ) | $300 |
| **ElastiCache Redis** | cache.t4g.micro | 2 nodes (Multi-AZ) | $50 |
| **S3 Storage** | Standard | 500 GB frames + 100 GB crops | $15 |
| **S3 Data Transfer** | 10 GB/month egress | - | $0.90 |
| **CloudWatch Logs** | Ingestion + storage | 50 GB/month | $25 |
| **CloudWatch Metrics** | Custom metrics | 50 metrics | $5 |
| **AWS Secrets Manager** | 4 secrets | - | $4 |
| **KMS Key Encryption** | 1 key | - | $1 |
| **VPC Data Transfer** | Cross-AZ | ~5 GB/month | $0.50 |
| **NAT Gateway** | 1 | - | $32 |
| **Data Transfer Out** | 100 GB/month | - | $9 |
| **ACM Certificate** | 1 domain | - | $0 |
| **Route 53** | - | - | $0.50 |
| **---** | | **Total** | **~$910/month** |

### Cost Optimizations

- **Spot Instances:** Use for Celery workers (70% discount)
- **Reserved Capacity:** Reserve 1 year for base ECS tasks (30% discount)
- **Data Lifecycle:** Archive old S3 data to Glacier after 90 days (70% cheaper)
- **Log Retention:** Reduce CloudWatch retention from 30→14 days (save $5/month)

---

## Maintenance & Upgrades

### Scheduled Maintenance Windows

- **Database:** Sunday 2–4 AM UTC (weekly patching possible)
- **Kubernetes/ECS:** First Tuesday of month (if needed)
- **OS Patching:** Monthly (auto via ECS task updates)
- **Library Patching:** Continuous (via dependabot PRs)
- **Certificate Renewal:** Auto (90 days before expiration via ACM)

### Patching Strategy

1. **Security Patches:** Deploy immediately (max 24hr)
2. **Bug Fix Patches:** Weekly rollup (every Monday)
3. **Minor Version Upgrades:** Monthly (during maintenance window)
4. **Major Version Upgrades:** Quarterly (with full testing)

---

## Key Takeaways

| Aspect | Approach |
|--------|----------|
| **Deployment Safety** | Blue-green (zero downtime, instant rollback) |
| **Infrastructure** | Terraform IaC (reproducible, version-controlled) |
| **Database HA** | RDS Multi-AZ with automatic failover |
| **Caching** | Redis Multi-AZ with cluster mode |
| **Monitoring** | CloudWatch dashboards + alarms → PagerDuty |
| **Secrets** | AWS Secrets Manager with KMS encryption |
| **Backups** | Hourly RDS snapshots + continuous transaction logs |
| **CI/CD** | GitHub Actions (fully automated) |
| **Scaling** | ECS autoscaling (CPU, memory thresholds) |
| **Security** | HTTPS, security groups, IRSA, least-privilege IAM |
| **Compliance** | CloudTrail audit logging, encryption, access controls |

---

**Last Updated:** 2026-05-28
**Maintained by:** DevOps Team
**Status:** Production-ready
