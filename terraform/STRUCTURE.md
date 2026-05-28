# Terraform Directory Structure

Complete layout of all Infrastructure-as-Code files for ANPR.

```
terraform/
├── versions.tf                          # Terraform version, provider requirements
├── variables.tf                         # Root variables (environment, size, secrets)
├── main.tf                              # Root module orchestration
├── README.md                            # Complete deployment & operations guide
├── DEPLOYMENT_GUIDE.md                  # Step-by-step deployment walkthrough
├── COST_BREAKDOWN.md                    # Cost analysis & optimization
├── STRUCTURE.md                         # This file
│
├── modules/
│   ├── vpc/
│   │   ├── main.tf                      # VPC, subnets, NAT, security groups, flow logs
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── rds/
│   │   ├── main.tf                      # RDS PostgreSQL, parameter groups, KMS, alarms
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── elasticache/
│   │   ├── main.tf                      # Redis replication group, auth, KMS, alarms
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── ecs/
│   │   ├── main.tf                      # ECS cluster, task definition, service, autoscaling
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── alb/
│   │   ├── main.tf                      # ALB, target groups, listeners, S3 logging
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── s3/
│   │   ├── main.tf                      # S3 buckets, encryption, versioning, lifecycle
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── secrets/
│   │   ├── main.tf                      # Secrets Manager, auto-rotation
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   └── monitoring/
│       ├── main.tf                      # CloudWatch dashboard, SNS topic
│       ├── variables.tf
│       └── outputs.tf
│
├── environments/
│   ├── dev/
│   │   └── terraform.tfvars             # Dev environment overrides
│   ├── stage/
│   │   └── terraform.tfvars             # Stage environment overrides
│   └── prod/
│       └── terraform.tfvars             # Production environment overrides
│
└── docs/
    ├── architecture.md                  # System architecture diagram
    ├── network_topology.png             # VPC layout
    └── runbooks/
        ├── HIGH_CPU.md                  # Incident: high ECS CPU
        ├── DB_CONNECTION_TIMEOUT.md     # Incident: database timeout
        └── REDIS_EVICTIONS.md           # Incident: Redis memory pressure
```

## File Purposes

### Root Level

| File | Purpose | ~Lines |
|------|---------|--------|
| `versions.tf` | Terraform version, AWS provider, state backend config | 20 |
| `variables.tf` | All configurable variables (environment, sizing, secrets) | 400 |
| `main.tf` | Orchestrates modules, passes variables, outputs endpoints | 200 |

### Modules

#### vpc/main.tf (200 lines)
- VPC with CIDR
- Public subnets (ALB, NAT)
- Private subnets (ECS, RDS, Redis)
- Internet Gateway
- NAT Gateways (one per AZ for HA)
- Route tables (public & private)
- NACLs (network ACLs)
- VPC Flow Logs for audit

#### rds/main.tf (350 lines)
- Parameter group (SSL required, logging, pgaudit)
- Subnet group (private subnets)
- Security group (ECS -> RDS access)
- RDS instance (Multi-AZ, automated backups, encrypted)
- KMS key for encryption
- RDS Proxy (connection pooling)
- CloudWatch alarms (CPU, connections, storage)

#### elasticache/main.tf (250 lines)
- Security group (ECS/Celery -> Redis)
- Subnet group (private subnets)
- Parameter group (eviction policy, timeouts)
- Replication group (primary + replica, HA)
- KMS encryption
- Auth token requirement
- CloudWatch alarms (CPU, memory, evictions, swap)

#### ecs/main.tf (350 lines)
- Security group (ALB -> ECS, ECS -> RDS/Redis/S3)
- CloudWatch log group
- ECS cluster (Container Insights enabled)
- IAM roles (execution + task roles, least privilege)
- ECS task definition (environment vars, secrets from Secrets Manager)
- ECS service (health checks, blue-green deployment)
- Auto-scaling (CPU, memory targets)

#### alb/main.tf (250 lines)
- Security group (0.0.0.0/0 -> 80/443)
- S3 bucket for ALB logs
- ALB (HTTP/2, cross-zone)
- Target group (health checks on /health)
- HTTP listener (redirect to HTTPS)
- HTTPS listener (ACM certificate)
- CloudWatch alarms (unhealthy targets, response time, 5xx errors)

#### s3/main.tf (200 lines)
- KMS key for encryption
- 3 buckets (frames, crops, audit)
- Versioning (all buckets)
- Encryption (KMS)
- Public access block (all blocked)
- Lifecycle policies (transition to IA/Glacier, expiration)
- Bucket policies (enforce SSL, deny unencrypted uploads)
- Access logging (to separate logging bucket)

#### secrets/main.tf (100 lines)
- Secrets Manager secrets (DB, JWT, app, Celery)
- Secret versions with values
- Auto-rotation for database password
- KMS policy for secret access

#### monitoring/main.tf (80 lines)
- SNS topic for alerts
- SNS email subscription
- CloudWatch dashboard (metrics for all components)
- CloudWatch log group for insights

## Module Dependencies

```
monitoring (no dependencies)
vpc (no dependencies)
secrets (depends on KMS key in root)
s3 (depends on KMS key in root)
alb (depends on: vpc)
rds (depends on: vpc, ecs [forward ref])
elasticache (depends on: vpc, ecs [forward ref])
ecs (depends on: vpc, alb, rds, elasticache, secrets, s3)
```

## Variable Hierarchy

Variables cascade from root to modules:

1. **root variables.tf**: Declare all possible variables
2. **environment/terraform.tfvars**: Set environment-specific values
3. **main.tf**: Pass variables to modules (overrides environment defaults)
4. **module/variables.tf**: Declare module-level variables
5. **module/main.tf**: Use variables in resource definitions

Example flow for `rds_instance_class`:
```
root/variables.tf: variable "rds_instance_class" { default = "db.t4g.medium" }
environments/prod/terraform.tfvars: rds_instance_class = "db.r6g.xlarge"
root/main.tf: rds_instance_class = var.rds_instance_class
modules/rds/variables.tf: variable "instance_class" { type = string }
modules/rds/main.tf: instance_class = var.instance_class
```

## Sensitive Variables

Marked with `sensitive = true` to prevent logging:
- `database_password`
- `jwt_secret`
- `secret_key`
- `celery_encryption_key`
- `redis_auth_token`

**Never commit these to git.** Pass via:
```bash
terraform apply \
  -var="database_password=..." \
  -var="jwt_secret=..." \
  ...
```

Or use environment variables:
```bash
export TF_VAR_database_password=...
terraform apply
```

## Resource Count

Total resources created by Terraform:

| Category | Count |
|----------|-------|
| VPC & Networking | 20 (VPC, subnets, IGW, NAT, route tables, NACLs) |
| Security | 15 (Security groups, IAM roles, policies) |
| Database | 10 (RDS instance, proxy, parameter group, KMS, alarms) |
| Caching | 8 (Redis, parameter group, KMS, alarms) |
| Compute | 15 (ECS cluster, service, task definition, autoscaling) |
| Load Balancing | 8 (ALB, target group, listeners, S3 logs) |
| Storage | 6 (S3 buckets, lifecycle, encryption) |
| Secrets | 8 (4 secrets × 2 versions/rotation) |
| Monitoring | 12 (CloudWatch alarms, dashboard, SNS, logs) |
| **Total** | **~100 resources** |

## Terraform State

State file tracks all 100 resources.

**Local state** (dev):
```bash
terraform state list | wc -l  # 100 resources
```

**Remote state** (prod - recommended):
```bash
# Store in S3 with DynamoDB lock
terraform {
  backend "s3" {
    bucket         = "anpr-state-prod"
    key            = "terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "anpr-state-lock"
    encrypt        = true
  }
}
```

## Code Quality

### Validation

```bash
# Syntax check
terraform validate

# Format check
terraform fmt -recursive

# Linting (using tflint)
tflint --init
tflint
```

### Security Scanning

```bash
# Scan for security issues (using checkov)
checkov -d terraform/

# Or use Snyk
snyk iac test terraform/
```

### Testing

Use Terratest for integration tests:

```go
package test

import (
    "testing"
    "github.com/gruntwork-io/terratest/modules/terraform"
)

func TestANPRInfrastructure(t *testing.T) {
    opts := &terraform.Options{
        TerraformDir: "../terraform/environments/dev",
    }
    
    terraform.InitAndApply(t, opts)
    defer terraform.Destroy(t, opts)
    
    // Assert outputs
    alb_dns := terraform.Output(t, opts, "alb_dns_name")
    // Verify ALB is accessible
}
```

## Common Operations

### Plan & Apply

```bash
# Review changes
terraform plan -var-file="environments/prod/terraform.tfvars" \
  -var="database_password=..." \
  -out=anpr.tfplan

# Apply changes
terraform apply anpr.tfplan

# Auto-approve (dangerous, don't use in prod)
terraform apply -auto-approve
```

### Inspect Resources

```bash
# List all resources
terraform state list

# Show specific resource
terraform state show aws_rds_cluster_instance.main

# Show outputs
terraform output
```

### Modify Infrastructure

```bash
# Add new resource
# 1. Add resource block to appropriate module/main.tf
# 2. Run plan to preview
terraform plan ...

# 3. Apply
terraform apply ...

# Remove resource
# 1. Remove resource block
# 2. Plan will show destroy
terraform plan ...

# 3. Apply
terraform apply ...

# Taint resource (force recreate)
terraform taint aws_rds_db_instance.main
terraform apply
```

### Update Secrets

```bash
# Rotate database password
aws secretsmanager rotate-secret --secret-id anpr/database

# Manual rotation via Terraform
terraform apply \
  -var="database_password=<NEW_PASSWORD>" ...

# Update RDS password after Terraform
aws rds modify-db-instance \
  --db-instance-identifier anpr-db \
  --master-user-password <NEW_PASSWORD> \
  --apply-immediately
```

---

**Total lines of Terraform code: ~2,500 lines**

All code follows:
- Terraform best practices (modular, DRY, documented)
- AWS security best practices (least privilege, encryption, auditing)
- Production-grade standards (HA, backups, monitoring, alerting)
