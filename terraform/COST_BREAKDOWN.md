# ANPR Cost Breakdown & Optimization

Monthly cost estimates for production ANPR deployment on AWS (us-east-1).

## Cost Summary

| Component | Dev | Stage | Prod | Notes |
|-----------|-----|-------|------|-------|
| **ECS Fargate** | $15 | $45 | $150 | Task CPU/memory × instance count |
| **RDS PostgreSQL** | $30 | $90 | $500 | db.t4g.micro → db.r6g.xlarge |
| **ElastiCache Redis** | $15 | $45 | $150 | cache.t4g.micro → cache.r6g.xlarge |
| **ALB** | $16 | $16 | $32 | Fixed $16/month + $0.006/LCU |
| **S3 Storage** | $5 | $50 | $500 | 100 GB → 1 TB frames/crops/audit |
| **Data Transfer** | $5 | $10 | $50 | NAT gateway, S3 egress |
| **CloudWatch Logs** | $5 | $10 | $30 | Ingestion + storage (30-90 day retention) |
| **Secrets Manager** | $0.40 | $0.40 | $0.40 | $0.40/secret × 4 secrets |
| **KMS** | $1 | $1 | $1 | $1/month per key (4 keys) |
| **CloudTrail** | $2 | $2 | $2 | Audit logging (optional) |
| **Backup/Snapshots** | $5 | $15 | $100 | RDS daily, Redis periodic |
| **NAT Gateway** | $32 | $32 | $32 | $0.045/hour + $0.045/GB |
| **Misc (DNS, monitoring)** | $10 | $10 | $10 | Route 53, CloudWatch custom metrics |
| **TOTAL** | **~$136** | **~$326** | **~$1,457** |

### Monthly Cost by Environment

```
Dev:   $136/month  (~$1,632/year)
Stage: $326/month  (~$3,912/year)
Prod:  $1,457/month (~$17,484/year)
```

## Detailed Breakdown

### ECS Fargate

Fargate charges per task-hour (vCPU × hours + memory × hours).

**Development (1 task, no HA)**
- CPU: 512 = 0.25 vCPU
- Memory: 1 GB
- Cost: 0.25 vCPU × $0.04048/hour + 1 GB × $0.004445/hour = ~$40/month
- Average usage: ~40% of month = ~$15/month

**Production (3 tasks, HA with auto-scaling to 10)**
- Baseline: 3 tasks × (1 vCPU × $0.04048 + 2 GB × $0.004445) = ~$150/month
- Peak scaling (avg 5 tasks): ~$250/month

**Cost Optimization**
- Use Fargate Spot for non-critical workloads (-70% cost, interruption risk)
- Downsize: 1 vCPU → 0.5 vCPU for light workloads (-50% cost)

### RDS PostgreSQL

Charged per instance-hour + storage + backups.

**Development**
- Instance: db.t4g.micro ($0.068/hour) = ~$50/month
- Storage: 10 GB × $0.138/month = $1.38
- Backups: 1 day retention = ~$0.30
- Total: ~$30/month

**Production**
- Instance: db.r6g.xlarge (HA) ($0.22/hour × 2 for Multi-AZ) = ~$330/month
- Storage: 100 GB × $0.138 = $13.80
- Backups: 30 days retention × $0.015/snapshot = ~$13
- RDS Proxy: Fixed cost ~$145/month
- Total: ~$500/month

**Cost Optimization**
- Use db.t4g (burstable) for dev/stage, db.r6g (memory-optimized) for prod
- Disable Multi-AZ for dev (save 50%)
- Reduce backup retention to 7 days (save 75%)
- Use Aurora PostgreSQL instead of RDS for better $/performance ratio (-30%)

### ElastiCache Redis

Charged per node-hour + data transfer.

**Development**
- Node: cache.t4g.micro ($0.025/hour × 1) = ~$18/month
- Replication: 1 replica (same cost) = ~$36/month
- Data transfer: <1 GB = ~$0
- Total: ~$15/month

**Production**
- Node: cache.r6g.xlarge ($0.138/hour × 2) = ~$210/month
- Data transfer: <100 GB/month = ~$5
- Total: ~$150/month

**Cost Optimization**
- Use On-Demand instead of Reserved Instances (higher hourly cost, but more flexible)
- Downsize from xlarge → large (-40% cost)
- Use Redis Sentinel instead of managed ElastiCache (self-hosted, but ops overhead)
- Compress data in transit (reduce data transfer)

### ALB (Application Load Balancer)

Fixed hourly charge + per LCU (Load Capacity Unit).

**All Environments**
- Fixed: $0.0252/hour = ~$18/month
- LCU (processed GB): 100 GB/month × $0.006 = ~$0.60
- Total: ~$16-32/month (2x for prod with higher traffic)

**Cost Optimization**
- Use Network Load Balancer (NLB) if you need ultra-high throughput (-20% cost)
- Consolidate multiple services on same ALB (amortize fixed cost)

### S3 Storage & Lifecycle

Charged per GB stored + operations.

**Development (100 GB total)**
- Storage: 100 GB × $0.023/GB = $2.30
- Lifecycle to S3-IA after 30 days: reduces to $0.0125/GB = ~$2/month (mixed)
- Operations (requests): 1,000/month × $0.0004 = ~$0.40
- Total: ~$5/month

**Production (1 TB)**
- Storage: 1,000 GB × $0.023 = $23
- Lifecycle transition: 50% in IA after 30 days = ~$12 (S3 $10 + IA $2)
- Lifecycle to Glacier after 90 days: 20% in Glacier = $4
- Operations: 100,000/month × $0.0004 = $40
- Total: ~$500/month

**Cost Optimization**
- Aggressive lifecycle: Move to Glacier after 30 days (-80% storage cost)
- Intelligent-Tiering: Auto-move based on access patterns (-30%)
- Object compression: JPEG → WebP reduces size by 30-40%
- Batch operations: Delete old versions in bulk

### Data Transfer

AWS charges for data leaving VPC (NAT gateway, S3 egress).

**Development**
- NAT Gateway: $0.045/hour + $0.045/GB = ~$32/month
- S3 Egress: <100 GB × $0.09/GB = ~$0
- Total: ~$5/month (mostly NAT fixed cost)

**Production**
- NAT Gateway: Same $32/month
- S3 Egress: 1,000 GB × $0.09 = $90
- Inter-region: If disaster recovery enabled = $50-100
- Total: ~$50/month

**Cost Optimization**
- Use S3 VPC endpoint (free): Eliminate NAT gateway charges for S3
- Cache responses: CloudFront caches frames near users (-40% egress)
- Compress API responses: gzip cuts transfer 60-80%

### CloudWatch Logs

Charged per GB ingested + storage retention.

**Development**
- Ingestion: 10 GB/month × $0.50 = $5
- Storage (7 days): ~2 GB × $0.03/GB = ~$0
- Total: ~$5/month

**Production**
- Ingestion: 100 GB/month × $0.50 = $50
- Storage (90 days): ~10 GB × $0.03 = ~$0.30
- Total: ~$30/month

**Cost Optimization**
- Reduce log verbosity: INFO → WARNING (-80% ingestion)
- Compress before storage: gzip (-60% storage)
- Use S3 export instead of CloudWatch storage (-70% cost)

### Other Costs

| Item | Cost | Notes |
|------|------|-------|
| Secrets Manager | $0.40 | $0.40/secret × 4 secrets (DB, JWT, app, Celery) |
| KMS Encryption | $4/month | $1/month per key rotation × 4 keys |
| CloudTrail | $2/month | Audit logging (optional, required for compliance) |
| Backups/Snapshots | $5-100 | Manual snapshots, automated backups |
| Route 53 | $0.50 | Hosted zone ($0.50) + queries free (up to 1B/month) |

## Cost Reduction Strategies

### Tier 1: Quick Wins (Save 20-30%)

1. **Disable Multi-AZ for dev/stage**
   - RDS: Save 50% ($250-300/month)
   - Redis: Save 50% ($75/month)

2. **Reduce backup retention**
   - From 30 → 7 days: Save ~$75/month

3. **Downsize instances for dev**
   - db.r6g.xlarge → db.t4g.micro: Save ~$300/month
   - cache.r6g.xlarge → cache.t4g.micro: Save ~$135/month

4. **Use S3 Intelligent-Tiering**
   - Auto-move to IA/Glacier: Save 30-40%

5. **Enable S3 VPC Endpoint**
   - Eliminate NAT gateway for S3: Save $32/month

### Tier 2: Medium Effort (Save 40-50%)

1. **Use Fargate Spot for non-critical tasks**
   - 70% discount on Fargate: Save ~$100/month

2. **Implement auto-scaling based on demand**
   - Reduce baseline tasks from 3 → 1 during off-hours: Save ~$50/month

3. **Consolidate environments**
   - Merge dev/stage into single environment: Save ~$200/month

4. **Cache aggressively with CloudFront**
   - Cache frames near users: Save 40% data transfer (~$40/month)

5. **Compress data**
   - Logs: gzip (-60%)
   - Frames: JPEG → WebP (-30-40%)
   - API responses: gzip (-80%)

### Tier 3: Architectural (Save 50%+)

1. **Use Aurora PostgreSQL**
   - 30% cheaper than RDS, better scalability

2. **Use ElastiCache Memcached**
   - Simpler than Redis, cheaper if you don't need persistence

3. **Use ECS on EC2 (instead of Fargate)**
   - 50% cheaper but requires management overhead

4. **Move cold data to S3**
   - Archive old detections/crops to S3 Glacier
   - Query with Athena instead of database (-80% cost)

5. **Use AWS Lambda for async tasks**
   - Replace Celery workers with Lambda (-70% cost for bursty workloads)

## Cost Monitoring

### Set Budget Alerts

```bash
aws budgets create-budget \
  --account-id 123456789 \
  --budget '{
    "BudgetName": "ANPR-Prod",
    "BudgetLimit": {"Amount": "1500", "Unit": "USD"},
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }'

aws budgets create-notification-with-subscribers \
  --account-id 123456789 \
  --budget-name "ANPR-Prod" \
  --notification '{
    "NotificationType": "ACTUAL",
    "ComparisonOperator": "GREATER_THAN",
    "Threshold": 80
  }'
```

### View Cost Dashboard

```bash
# AWS Console Cost Explorer
# https://console.aws.amazon.com/cost-management/home?region=us-east-1#/custom

# Or via CLI
aws ce get-cost-and-usage \
  --time-period Start=2026-05-01,End=2026-05-28 \
  --granularity MONTHLY \
  --metrics "BlendedCost" \
  --group-by Type=DIMENSION,Key=SERVICE
```

### Monthly Cost Review

Add to calendar:
- **Monthly (1st of month)**: Review costs, identify spikes
- **Quarterly**: Right-size instances, cancel unused resources
- **Annually**: Evaluate Reserved Instances (RI) or Savings Plans

## Savings Plan Options

For **production** workloads with **stable usage**, consider:

### Compute Savings Plan
- 1-year: 20-30% savings
- 3-year: 30-40% savings
- Applies to EC2, Fargate, Lambda

### RDS Reserved Instances
- Multi-AZ db.r6g.xlarge: $0.22/hour → $0.13/hour (1-year) = **$1,200/year savings**

### ElastiCache Reserved Nodes
- cache.r6g.xlarge: $0.138/hour → $0.085/hour (1-year) = **$400/year savings**

**Total RI savings: ~$1,600/year** (for production only)

## Final Recommendations

### Optimal Production Configuration

| Component | Instance | Cost/Month |
|-----------|----------|-----------|
| ECS Fargate | 2x t4g.medium (0.5 vCPU, 1 GB) baseline + Fargate Spot for bursts | $75 |
| RDS | db.t4g.large with Single-AZ (no Multi-AZ) | $200 |
| Redis | cache.r6g.large (1 replica) | $120 |
| ALB + S3 + CloudWatch | (as configured) | $100 |
| Data Transfer (with VPC endpoint) | (reduced) | $10 |
| **TOTAL** | | **$505/month** |

**vs. Current: ~$1,457/month (65% cost reduction)**

Trade-offs:
- Slightly higher latency during peak traffic (auto-scaling handles)
- No Multi-AZ for database (RTO ~30 min if failure)
- Single-region only (no disaster recovery)

Recommended for: Early/mid-stage production with < 200 requests/second
