# Cost Optimization Module

Provides Infrastructure-as-Code for ANPR backend cost optimization, including:
- ECS autoscaling (CPU/memory-based)
- Scheduled scaling (off-peak downscaling)
- S3 Intelligent-Tiering and lifecycle policies
- VPC endpoints for S3/CloudWatch (NAT bypass)
- CloudWatch alarms for monitoring optimization effectiveness

## Usage

```hcl
module "cost_optimization" {
  source = "./modules/cost_optimization"

  # Global flags
  enable_cost_optimization   = true   # Enable all features
  enable_scheduled_scaling   = true   # Off-peak scaling
  enable_intelligent_tiering = true   # S3 lifecycle

  # ECS configuration
  cluster_name     = aws_ecs_cluster.main.name
  service_name     = aws_ecs_service.api.name
  ecs_min_capacity = 1
  ecs_max_capacity = 5

  # S3 configuration
  s3_bucket_frames_id       = aws_s3_bucket.frames.id
  s3_bucket_crops_id        = aws_s3_bucket.crops.id
  s3_bucket_audit_id        = aws_s3_bucket.audit.id
  s3_lifecycle_archive_days = 30
  s3_lifecycle_delete_days  = 90

  # VPC configuration
  vpc_id                   = aws_vpc.main.id
  vpc_cidr                 = "10.0.0.0/16"
  private_route_table_ids  = [aws_route_table.private.id]
  private_subnet_ids       = aws_subnet.private[*].id

  # Alerting
  alarm_sns_topic_arn = aws_sns_topic.alerts.arn

  # Tagging
  project_name = "anpr"
  environment  = "prod"
  aws_region   = "us-east-1"

  # Service dependency (for Terraform ordering)
  service_dependency = aws_ecs_service.api
}
```

## Features

### 1. ECS Autoscaling
- **CPU-based:** Scales out at 70% CPU, scales in at 40%
- **Memory-based:** Scales out at 80% memory
- **Cooldowns:** 60s scale-out (quick response), 300s scale-in (avoid oscillation)

**Cost Impact:** Reduces peak cost from 5 tasks constant → 1–5 tasks dynamic
- Baseline: 1 task = $5/month
- Peak: 5 tasks = $25/month
- Amortized: ~$15/month

### 2. Scheduled Scaling (Off-Peak)
- **Scale down:** 9 PM UTC (off-peak hours)
- **Scale up:** 6 AM UTC (on-peak hours)
- **Impact:** 9 hours/day × 4 tasks saved = $12/month

**Enable for:** prod/stage only (dev may have 24/7 activity)

### 3. S3 Intelligent-Tiering & Lifecycle
- **Automatic tiering:** Objects move Standard → IA → Deep Archive
- **Lifecycle deletion:** GDPR compliance (delete after retention period)
- **Buckets covered:** frames, crops, audit logs

**Cost Breakdown (100 GB/month):**
| Storage Class | Days | Cost |
|---|---|---|
| Standard | 0-30 | $2.30 |
| Standard-IA | 30-90 | $1.27 |
| Glacier | 90+ | $0.40 |
| **Total** | **30-90 days** | **$1.50–2.30** |

### 4. VPC Endpoints
- **S3 Gateway Endpoint:** Bypass NAT for S3 traffic (saves $0.045/GB)
- **CloudWatch Logs Interface Endpoint:** Direct connectivity to CloudWatch

**Cost Savings:** 
- 100 GB/month × $0.045/GB = $4.50/month
- Plus NAT hourly fee elimination

### 5. CloudWatch Alarms
- **CPU Not Scaling:** Alert if ECS CPU > 85% (scaling may be failing)
- **S3 Lifecycle Failure:** Alert if old objects not archived (>10k unarchived)

## Configuration by Environment

### Dev (Minimal)
```hcl
enable_cost_optimization   = false  # No optimization overhead
enable_scheduled_scaling   = false  # Need 24/7 for testing
enable_intelligent_tiering = true   # Low-cost storage for long-term data

ecs_min_capacity = 1
ecs_max_capacity = 2
```

### Stage (Production-Like)
```hcl
enable_cost_optimization   = true   # Test optimization features
enable_scheduled_scaling   = false  # Keep stable for testing
enable_intelligent_tiering = true

ecs_min_capacity = 1
ecs_max_capacity = 4
```

### Prod (Full Optimization)
```hcl
enable_cost_optimization   = true   # All features enabled
enable_scheduled_scaling   = true   # Off-peak downscaling
enable_intelligent_tiering = true

ecs_min_capacity = 1
ecs_max_capacity = 10  # Allow high peak
```

## Monitoring & Validation

### CloudWatch Metrics to Watch
```bash
# Check autoscaling behavior
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=anpr-api \
  --start-time 2026-05-28T00:00:00Z \
  --end-time 2026-05-29T00:00:00Z \
  --period 300 \
  --statistics Average,Maximum

# Check desired task count over time
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name DesiredTaskCount \
  --dimensions Name=ServiceName,Value=anpr-api \
  --start-time 2026-05-28T00:00:00Z \
  --end-time 2026-05-29T00:00:00Z \
  --period 300 \
  --statistics Average
```

### S3 Lifecycle Verification
```bash
# Check storage class distribution
aws s3api list-objects-v2 \
  --bucket anpr-frames \
  --prefix frames/ \
  --query 'Contents[].{Key:Key,Size:Size,StorageClass:StorageClass}' \
  | jq 'group_by(.StorageClass) | map({class: .[0].StorageClass, count: length})'

# Check for objects pending deletion
aws s3api list-objects-v2 \
  --bucket anpr-frames \
  --prefix frames/ \
  --query 'Contents[?LastModified < `2026-03-01`].{Key:Key,LastModified:LastModified}'
```

### Cost Validation
```bash
# Check actual vs. budgeted costs
aws ce get-cost-and-usage \
  --time-period Start=2026-05-01,End=2026-06-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
```

## Maintenance

### Quarterly Cost Optimization Review
- [ ] Review actual vs. budgeted cost (AWS Cost Explorer)
- [ ] Check RDS CPU/memory (target: 40–60% avg, <80% peak)
- [ ] Verify ECS scaling behavior (CPU-triggered, not time-based)
- [ ] Confirm S3 objects are being archived (Standard → IA → Glacier progression)
- [ ] Audit for orphaned resources (old snapshots, unused security groups)
- [ ] Validate VPC endpoint usage (should reduce NAT data transfer by 90%+)
- [ ] Check Reserved Instance coverage (target: 60% of baseline)

### Troubleshooting

**Issue:** ECS not scaling despite high CPU
- **Solution:** Check `ecs_max_capacity` limit; may be reached. Verify `aws_appautoscaling_target` exists (enabled via flag).

**Issue:** S3 objects not being archived
- **Solution:** Enable `enable_intelligent_tiering = true`. Verify lifecycle rules are active: `aws s3api get-bucket-lifecycle-configuration --bucket <bucket>`.

**Issue:** Unexpected NAT charges still high
- **Solution:** Verify S3 VPC endpoint exists and is attached to private route tables: `aws ec2 describe-vpc-endpoints --filters Name=service-name,Values=*s3`.

## Cost Savings Breakdown

**Over-Provisioned Baseline (Current):**
- ECS: $150–200/month
- RDS: $100–150/month
- ElastiCache: $30–40/month
- S3: $5–10/month
- **Total: $285–400/month**

**Optimized Configuration (With Module):**
- ECS: $15–20/month (1-task baseline + autoscaling)
- RDS: $25–30/month (db.t3.small + gp3)
- ElastiCache: $8–12/month (1-node single-AZ)
- S3: $3–5/month (intelligent-tiering + lifecycle)
- **Total: $51–67/month**

**With 1-Year Reserved Instances (60% discount):**
- ECS: $8–10/month
- RDS: $15–18/month
- ElastiCache: $4–6/month
- **Subtotal: $27–34/month**
- Plus variable costs: $25–35/month
- **Total: $52–69/month**

**Savings: 78–82% cost reduction = $216–348/month recurring**

## Module Dependencies

This module depends on:
- `aws_ecs_cluster` (for ECS cluster name)
- `aws_ecs_service` (for service name)
- `aws_s3_bucket` (for S3 bucket IDs)
- `aws_vpc` (for VPC ID and routing)
- `aws_sns_topic` (optional, for alarms)

## Outputs

```hcl
# Autoscaling configuration
autoscaling_target_arn = "arn:aws:autoscaling:us-east-1:123456789:scalable-target/..."
cpu_scaling_policy_arn = "arn:aws:autoscaling:us-east-1:123456789:scaling-policy/..."

# VPC endpoints
s3_endpoint_id = "vpce-123456789"
cloudwatch_endpoint_id = "vpce-987654321"

# Cost optimization summary
cost_optimization_summary = {
  autoscaling_enabled = true
  scheduled_scaling_enabled = true
  intelligent_tiering_enabled = true
  ecs_min_capacity = 1
  ecs_max_capacity = 10
  s3_archive_days = 30
  s3_delete_days = 90
  vpc_endpoint_s3_enabled = true
  estimated_savings = "78% reduction from baseline"
}
```

## Further Reading

- [AWS ECS Autoscaling Documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html)
- [S3 Intelligent-Tiering](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intelligent-tiering.html)
- [VPC Endpoints for AWS Services](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints.html)
- [AWS Cost Optimization Best Practices](https://docs.aws.amazon.com/aws-cost-management/latest/userguide/best-practices.html)
