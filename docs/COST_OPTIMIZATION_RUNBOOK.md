# ANPR Cost Optimization Runbook

**Status:** Ready for Implementation (Phase 0)  
**Target Savings:** 78% cost reduction ($235–340/month)  
**Implementation Timeline:** 4 weeks  
**Baseline Cost:** $285–400/month (current over-provisioned config)  
**Optimized Cost:** $60–80/month baseline + $10–20/month peak overage

---

## Quick Start

### Week 1: Downsize Core Infrastructure
1. Update `terraform/environments/prod/terraform.tfvars`:
   - ECS: 1024 CPU → 256 CPU, 2048 MB → 512 MB
   - RDS: db.t4g.medium → db.t3.small, Multi-AZ disabled (dev/stage only)
   - ElastiCache: 2 nodes → 1 node

2. Deploy:
   ```bash
   cd terraform/environments/prod
   terraform plan -var-file=terraform.tfvars
   terraform apply -var-file=terraform.tfvars
   ```

3. Validate:
   ```bash
   # Load test: confirm 500 req/min @ <200ms p95
   locust -f tests/load_tests/locustfile.py -u 100 -r 10 -t 5m http://localhost:8000
   ```

### Week 2: Enable Autoscaling & S3 Optimization
1. Add cost optimization module to your infrastructure:
   ```bash
   # Copy provided terraform/modules/cost_optimization/ to your repo
   # Update main Terraform configuration to call the module
   ```

2. Enable in prod:
   ```hcl
   module "cost_optimization" {
     source = "./modules/cost_optimization"
     enable_cost_optimization = true
     ecs_min_capacity = 1
     ecs_max_capacity = 10
     # ... rest of config
   }
   ```

3. Deploy & test:
   ```bash
   terraform apply
   # Monitor CloudWatch: ECS should scale at 70% CPU
   ```

### Week 3: Spot Instances & Scheduled Scaling
1. Enable scheduled scaling in prod:
   ```hcl
   enable_scheduled_scaling = true
   ```

2. Confirm off-peak scaling works (9 PM → 1 task, 6 AM → 5 tasks max).

### Week 4: Reserved Instances
1. Buy 1-year RIs for baseline resources:
   - ECS: 256 CPU × 1 task
   - RDS: db.t3.small
   - ElastiCache: cache.t3.micro

2. Expected additional savings: 40–60% on baseline.

---

## Detailed Implementation Guide

### 1. Downsize ECS Task Definition

**Current (Over-Provisioned):**
```hcl
ecs_task_cpu     = 1024
ecs_task_memory  = 2048
ecs_desired_count = 2–5
```

**Optimized:**
```hcl
ecs_task_cpu     = 256
ecs_task_memory  = 512
ecs_desired_count = 1
ecs_min_capacity = 1
ecs_max_capacity = 10
```

**Why:** 256 CPU, 512 MB handles ~500 req/min (your peak). At 100 req/min baseline, CPU utilization ≈ 20%, memory ≈ 150 MB. Autoscaling adds more tasks as needed.

**Validation (Load Test):**
```bash
# Generate 100 req/min for 5 minutes
locust -f tests/load_tests/locustfile.py \
  -u 100 \                    # 100 concurrent users
  -r 10 \                     # Spawn 10 users/sec
  -t 5m \                     # 5-minute duration
  --headless \
  http://localhost:8000

# Expected: <200ms p95 latency, no errors
```

### 2. Downsize RDS Instance

**Current:**
```hcl
rds_instance_class = "db.t4g.medium"    # 2 vCPU, 2 GB RAM = $100–150/month
rds_multi_az = true                      # Multi-AZ adds $100+
rds_storage_type = "gp2"                 # Older, more expensive
```

**Optimized:**
```hcl
rds_instance_class = "db.t3.small"      # 2 vCPU, 2 GB RAM = $20–30/month
rds_multi_az = false                     # (disable for dev/stage)
rds_storage_type = "gp3"                 # $0.03/GB/hour vs gp2's $0.05
```

**Rationale:**
- db.t3.small handles 5,000 concurrent connections; you'll have ~50 at peak.
- Single-AZ acceptable for Phase 0; RTO = 30–60min (manual restore from snapshot).
- gp3 is same performance, cheaper.

**Post-Deployment:**
1. Monitor CloudWatch: RDS CPU should stay <70% avg (target: 40–60%)
2. If CPU consistently >70%, upgrade to db.t3.medium (but this won't happen at 100 req/min).
3. Phase 1: Add cross-AZ read replica for HA.

### 3. Consolidate ElastiCache

**Current:**
```hcl
elasticache_node_type = "cache.t4g.micro"
elasticache_num_cache_nodes = 2         # 2 nodes = $30–40/month
elasticache_automatic_failover = true   # Adds cost
```

**Optimized:**
```hcl
elasticache_node_type = "cache.t3.micro"
elasticache_num_cache_nodes = 1         # 1 node = $8–12/month
elasticache_automatic_failover = false
```

**Why:** cache.t3.micro = 0.5 GB memory. Phase 0 cache usage:
- Rate-limit tokens: ~1 MB
- Session cache: ~100 KB
- Detection queue: ~100 KB
- **Total: <250 KB** (plenty of headroom)

**Risk:** Single-node failure → 5min service restart (no persistence). Acceptable for Phase 0.  
**Phase 1 Mitigation:** Add 2-node cluster mode with automatic failover.

### 4. S3 Intelligent-Tiering & Lifecycle

**Add to Terraform:**
```hcl
module "cost_optimization" {
  enable_intelligent_tiering = true
  s3_lifecycle_archive_days = 30        # Move to Glacier
  s3_lifecycle_delete_days = 90         # GDPR compliance
}
```

**Behavior:**
- Objects in S3 Standard: $0.023/GB/month
- → After 30 days: Intelligent-Tiering automatically moves to IA ($0.0125/GB/month)
- → After 90 days: Moves to Deep Archive ($0.00099/GB/month)
- → After 90 days: Deleted (GDPR retention)

**Cost Impact (100 GB/month ingest):**
| Days | Storage Class | Cost |
|------|---------------|------|
| 0–30 | Standard | $2.30 |
| 30–90 | IA | $1.27 |
| 90+ | Deep Archive / Deleted | $0 |
| **Monthly Avg** | **All tiers** | **$0.80–1.50** |

### 5. VPC Endpoint for S3

**Add to Terraform:**
```hcl
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
}
```

**Why:** Eliminates NAT Gateway data transfer fees ($0.045/GB).
- Current: 100 GB/month × $0.045 = $4.50/month
- Plus NAT hourly fee ($0.32/hour × 730 hours ≈ $233/month)
- **Savings: $237.50/month** by bypassing NAT for S3

### 6. Enable ECS Autoscaling

**Module Outputs Autoscaling:**
```hcl
module "cost_optimization" {
  enable_cost_optimization = true
  ecs_min_capacity = 1      # Always keep 1 task running
  ecs_max_capacity = 10     # Allow up to 10 for peak
}
```

**Scaling Behavior:**
- **CPU 0–40%:** 1 task running
- **CPU 40–70%:** Scaling down (slowly, 5-min cooldown)
- **CPU 70–100%:** Scaling up (quickly, 1-min cooldown)
- **CPU >100% (shouldn't happen):** Max out at 10 tasks

**Expected Cost Curve:**
| Time of Day | CPU | Tasks | Cost/hour |
|-------------|-----|-------|-----------|
| Off-peak (9pm–6am) | 5% | 1 | $0.02 |
| Low activity (6am–8am) | 15% | 1 | $0.02 |
| Peak (8am–8pm) | 60% | 3–5 | $0.06–0.10 |
| Spike (1–2 hours) | 95% | 8–10 | $0.16–0.20 |

**Monthly Estimate:**
- Baseline: 1 task × 730 hours × $0.02048/hour = $15/month
- Peak: 4 tasks × 5 hours × $0.02048/hour = $0.40/month
- **Total: ~$15–20/month for ECS**

### 7. Enable Scheduled Scaling (Off-Peak)

**Requires:** Cost Optimization module with `enable_scheduled_scaling = true`

**Behavior:**
- **9 PM UTC:** Scale down to 1 task (ecs_max_capacity = 1)
- **6 AM UTC:** Scale back up (ecs_max_capacity = 10)

**Why:** ANPR typically runs 6 AM–9 PM. Off-peak has minimal ingest, can run on single task.

**Cost Saving:** 9 hours/day × 4 tasks × $0.02048/hour × 30 days = $22/month

**Adjust times for your timezone:**
```bash
# Convert to your timezone (e.g., IST = UTC+5:30)
# 9 PM UTC = 2:30 AM IST (next day)
# Edit terraform/modules/cost_optimization/main.tf:
#   schedule = "cron(30 2 ? * * *)"  # 2:30 AM IST
```

### 8. Purchase 1-Year Reserved Instances

**Recommendation:**
- ECS: 256 CPU, 512 MB (1 task baseline) × 1 year = ~$30 upfront
- RDS: db.t3.small × 1 year = ~$100 upfront
- ElastiCache: cache.t3.micro × 1 year = ~$35 upfront
- **Total Upfront: ~$165**
- **Monthly Savings: 40–60% on baseline**

**How to Calculate:**
```bash
# AWS Pricing Console: https://aws.amazon.com/ec2/pricing/reserved-instances/
# Or via CLI:
aws ec2 describe-reserved-instances-offerings \
  --filters "Name=instance-type,Values=t3.small" \
          "Name=offering-type,Values=All Upfront" \
          "Name=term,Values=31536000" \
  --output table
```

**Alternative: AWS Savings Plans** (more flexible)
- 1-year commitment for Fargate + RDS compute
- Can move between instance types
- 40–60% discount like RIs, but simpler

---

## Monitoring & Alerts

### Cost Monitoring Script

```bash
# Run monthly cost report
./scripts/cost_monitoring.sh monthly

# Forecast end-of-month cost
./scripts/cost_monitoring.sh forecast

# Validate optimization effectiveness
./scripts/cost_monitoring.sh validate-optimization
```

### CloudWatch Alarms

The cost optimization module creates alarms for:
1. **ECS CPU > 85% for 10 min** → Alert if autoscaling is failing
2. **S3 objects not archived** → Alert if lifecycle job is failing

Configure SNS topic for alerts:
```bash
aws sns create-topic --name anpr-cost-alerts
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:123456789:anpr-cost-alerts \
  --protocol email \
  --notification-endpoint ops@anpr.local
```

### Metrics to Track (Weekly)

| Metric | Target | Escalation |
|--------|--------|-----------|
| ECS Avg CPU | 40–60% | Page ops if >80% avg |
| RDS Avg CPU | 40–60% | Page ops if >70% avg |
| ECS Desired Count | 1–5 | Alert if stuck at max |
| S3 Standard Bytes | Decreasing | Alert if old objects not archived |
| Monthly Estimated Cost | <$120 | Alert if >$150 forecast |

---

## Risk Mitigation

### Risk: Database Performance Degradation

**Scenario:** db.t3.small is too small for peak load.

**Prevention:**
1. Load test before prod: simulate 500 req/min with realistic query patterns
2. Monitor CloudWatch metrics: RDS CPU, DB connections, I/O

**Response:**
- If RDS CPU >70% sustained: upgrade to db.t3.medium (small cost increase, large reliability gain)
- If peak response time >1s: add read replicas (Phase 1)

### Risk: Spot Instance Interruptions (Celery Workers)

**Scenario:** Spot instances get interrupted, delaying async tasks.

**Prevention:**
1. Celery jobs are idempotent (safe to retry)
2. Tasks spread across AZs (lower correlation)
3. Fallback capacity_provider = FARGATE (on-demand backup)

**Response:**
- Monitor CloudWatch: SpotInterruptionRate metric
- If >10% interruptions: increase FARGATE capacity (on-demand)

### Risk: Single-Node Redis Loss

**Scenario:** ElastiCache node fails, cache is lost.

**Prevention:**
1. Rate-limiting regenerated from DB on cache miss
2. Session cache repopulates in <5min
3. RDB snapshots enabled

**Response:**
- Service continues, just slower (60% cache miss = ~2s extra latency)
- Phase 1: upgrade to 2-node cluster mode (automatic failover)

### Risk: S3 Lifecycle Job Failure

**Scenario:** Old objects not deleted/archived due to job failure.

**Prevention:**
1. CloudWatch alarm: alert if >10k old objects
2. Test lifecycle rules in dev first
3. Audit log retention = 3 years (immutable)

**Response:**
- Manual cleanup: `aws s3 rm s3://bucket/frames/ --recursive --include "*.jpg" --exclude "*" --dryrun`
- Add fallback Lambda if lifecycle job keeps failing

---

## Validation Checklist

### Week 1 (Downsize Infrastructure)
- [ ] ECS task CPU/memory reduced (256 CPU, 512 MB)
- [ ] RDS instance class changed (db.t3.small)
- [ ] ElastiCache consolidated (1 node)
- [ ] Load test passes: 500 req/min @ <200ms p95
- [ ] RDS CPU <70% at peak
- [ ] Cost baseline established: <$120/month

### Week 2 (Autoscaling & S3 Optimization)
- [ ] Cost optimization module deployed
- [ ] ECS autoscaling works (CPU→scale up, cooldown→scale down)
- [ ] S3 Intelligent-Tiering enabled
- [ ] S3 lifecycle policies active (objects moved to IA after 30 days)
- [ ] VPC endpoint for S3 created (should reduce NAT charges)
- [ ] CloudWatch alarms created

### Week 3 (Spot Instances & Scheduled Scaling)
- [ ] Spot instances enabled for Celery workers
- [ ] Scheduled scaling enabled (9pm→1 task, 6am→scale up)
- [ ] Off-peak scaling verified in CloudWatch logs
- [ ] Cost estimate: $60–80/month baseline + $10–20 peak

### Week 4 (Reserved Instances)
- [ ] 1-year RIs purchased for baseline resources
- [ ] RI coverage documented (60% baseline on-demand)
- [ ] Final cost forecast: $52–69/month (with RIs + on-demand overages)
- [ ] Runbook documented: `docs/COST_OPTIMIZATION_RUNBOOK.md`
- [ ] Team trained on cost monitoring: `./scripts/cost_monitoring.sh`

---

## Post-Optimization Operations

### Daily (Automated)
- [ ] CloudWatch alarms trigger if anomalies detected
- [ ] S3 lifecycle jobs run (midnight UTC)

### Weekly
- [ ] Run cost monitoring: `./scripts/cost_monitoring.sh validate-optimization`
- [ ] Review CloudWatch dashboard: ECS scaling, RDS CPU, cost trends

### Monthly
- [ ] Run monthly cost report: `./scripts/cost_monitoring.sh monthly`
- [ ] Forecast end-of-month: `./scripts/cost_monitoring.sh forecast`
- [ ] Compare to budget; escalate if >10% over

### Quarterly
- [ ] Audit optimization effectiveness (CPU utilization, scaling behavior)
- [ ] Review cost drivers; identify next optimization opportunity
- [ ] Update RIs if scaling patterns changed
- [ ] Validate disaster recovery (RDS restore from snapshot)

---

## Appendix: Cost Comparison

### Before (Over-Provisioned)
```
ECS:          1024 CPU, 2048 MB × 2–5 tasks    = $150–200/month
RDS:          db.t4g.medium, Multi-AZ         = $100–150/month
ElastiCache:  cache.t4g.micro × 2, Multi-AZ   = $30–40/month
S3:           Standard + NAT transfer          = $5–10/month
Monitoring:   CloudWatch, Prometheus           = $10–20/month
─────────────────────────────────────────────────────────────────
TOTAL:        ~$295–420/month
```

### After (Optimized)
```
ECS:          256 CPU, 512 MB × 1–10 (auto)   = $15–20/month
RDS:          db.t3.small, Single-AZ          = $25–30/month
ElastiCache:  cache.t3.micro × 1              = $8–12/month
S3:           Intelligent-Tiering + Lifecycle = $3–5/month
VPC Endpoint: S3 Gateway (no NAT)              = $0/month
Monitoring:   CloudWatch + Alarms              = $5–10/month
─────────────────────────────────────────────────────────────────
SUBTOTAL:     ~$56–77/month

+ Peak overages (1–2 hours/day, extra 4–5 tasks):
              ~$10–20/month

+ RIs (60% discount on baseline, 1-year commitment):
              ~$150–200 upfront (amortized: $12–17/month)

─────────────────────────────────────────────────────────────────
TOTAL:        ~$52–69/month (with RIs) or $66–97/month (no RIs)

SAVINGS:      $225–348/month (78% reduction)
```

---

## Support & Escalation

**Questions or Issues?**

1. **Terraform:** Check `terraform validate` and `terraform plan` output
2. **AWS CLI:** Enable debug logging: `export AWS_DEBUG=true`
3. **CloudWatch:** Check logs for autoscaling errors: `/aws/ecs/anpr-api`
4. **Cost:** Review Cost Explorer: https://console.aws.amazon.com/cost-management/

**Escalation Path:**
- Dev issue → Debug locally (docker-compose)
- Stage/Prod issue → Check CloudWatch, RDS CloudWatch Events, AWS Health
- Cost overrun → Analyze Cost Explorer, check for orphaned resources

---

**Document Version:** 1.0  
**Last Updated:** 2026-05-28  
**Next Review:** 2026-08-28 (Q3 2026)
