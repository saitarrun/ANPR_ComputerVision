# Lambda Secrets Rotation Module

Terraform module for automatic RDS password rotation via AWS Secrets Manager and Lambda.

## Overview

This module creates a Lambda function that automatically rotates RDS master user passwords on a configurable schedule (default: 30 days). The rotation process is zero-downtime and audited for compliance with SOC 2 and PCI-DSS standards.

## Features

- **4-step atomic rotation**: Create → Set → Test → Finish
- **VPC-native**: Lambda runs in private subnets with restricted egress
- **Failure recovery**: Exponential backoff retry logic for transient failures
- **Comprehensive audit logging**: CloudWatch Logs with CloudWatch alarms
- **Security hardened**:
  - Least-privilege IAM role (specific RDS instance + secret)
  - No plaintext secrets in logs or environment
  - SSL/TLS encryption for all data in transit
  - KMS encryption for secrets at rest

## Module Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `project_name` | string | — | Project name for resource naming |
| `environment` | string | prod | dev/staging/prod |
| `rds_instance_id` | string | — | RDS instance identifier (e.g., `anpr-db`) |
| `db_secret_id` | string | — | Secrets Manager secret ID |
| `db_secret_arn` | string | — | Secrets Manager secret ARN |
| `rds_security_group_id` | string | — | RDS security group ID (for Lambda egress) |
| `vpc_id` | string | — | VPC ID for Lambda placement |
| `private_subnet_ids` | list(string) | — | Private subnet IDs for Lambda VPC |
| `rotation_days` | number | 30 | Days between rotations (1–365) |
| `rotation_schedule_expression` | string | "" | Optional cron expression |
| `log_level` | string | INFO | DEBUG/INFO/WARNING/ERROR |
| `log_retention_days` | number | 30 | CloudWatch log retention |
| `sns_topic_arn` | string | — | SNS topic for alerts |

## Module Outputs

| Output | Description |
|--------|-------------|
| `lambda_function_arn` | ARN of rotation Lambda function |
| `lambda_function_name` | Name of rotation Lambda function |
| `lambda_role_arn` | ARN of Lambda execution role |
| `rotation_schedule` | Rotation schedule configuration |
| `cloudwatch_log_group` | CloudWatch log group name |
| `security_group_id` | Lambda security group ID |

## Usage

```hcl
module "lambda_rotate" {
  source = "./modules/lambda_rotate"

  project_name           = "anpr"
  environment            = "prod"
  rds_instance_id        = module.rds.db_instance_id
  db_secret_id           = module.secrets.db_secret_id
  db_secret_arn          = module.secrets.db_secret_arn
  rds_security_group_id  = module.rds.rds_security_group_id
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnet_ids
  rotation_days          = 30
  log_level              = "INFO"
  log_retention_days     = 30
  sns_topic_arn          = module.monitoring.sns_topic_arn
}
```

## Architecture

```
AWS Secrets Manager (AWSCURRENT: old password)
         ↓ [30-day trigger]
         ↓
Lambda Function (rotate_secret.py)
    Step 1: Create (generate new password → AWSPENDING)
    Step 2: Set (update RDS master password)
    Step 3: Test (verify new password works)
    Step 4: Finish (promote AWSPENDING → AWSCURRENT)
         ↓
RDS PostgreSQL (password updated immediately)
         ↓
ECS Applications (refresh credentials on next poll)
```

## Rotation Process

### Step 1: Create (< 1 second)
1. Generate random 32-character password
2. Validate against RDS requirements
3. Store as `AWSPENDING` version in Secrets Manager
4. **Risk**: None—production system unchanged

### Step 2: Set (10–30 seconds)
1. Retrieve `AWSPENDING` secret (new password)
2. Call `ModifyDBInstance` to update RDS master password
3. RDS applies change immediately
4. **Risk**: Low—both passwords briefly valid

### Step 3: Test (5–10 seconds)
1. Retrieve `AWSPENDING` secret
2. Open PostgreSQL connection to RDS
3. Execute `SELECT 1` verification query
4. **Risk**: None—read-only query, no data modified

### Step 4: Finish (< 1 second)
1. Move `AWSPENDING` → `AWSCURRENT` in Secrets Manager
2. Old version kept as `AWSPREVIOUS` (7-day retention)
3. **Risk**: None—Secrets Manager change only

## Lambda Deployment

### Build Dependencies

The Lambda function requires `psycopg2` (boto3 is included in runtime).

**Build the Lambda layer**:
```bash
cd /path/to/project
bash lambda/build_layer.sh
```

This creates a layer zip at `terraform/modules/lambda_rotate/.terraform/lambda-layer.zip`.

**In CI/CD pipeline**, automate this:
```bash
pip install -r lambda/requirements.txt -t lambda_layer/python/lib/python3.11/site-packages/
zip -r terraform/modules/lambda_rotate/.terraform/lambda-layer.zip lambda_layer/
```

### Deploy with Terraform

```bash
terraform init
terraform plan -target module.lambda_rotate
terraform apply -target module.lambda_rotate
```

## Manual Testing

### Trigger a Test Rotation

```bash
bash terraform/modules/lambda_rotate/test_rotation.sh anpr/database anpr-db
```

This script:
1. Verifies prerequisites (AWS CLI, jq, permissions)
2. Checks secret and RDS instance exist
3. Triggers rotation
4. Polls for completion (2-minute timeout)
5. Displays final version state

### Monitor Rotation Logs

```bash
aws logs tail /aws/lambda/anpr-secrets-rotation --follow
```

### Check Rotation Status

```bash
aws secretsmanager describe-secret \
  --secret-id anpr/database \
  --query 'VersionIdsToStages'
```

Expected after successful rotation:
```json
{
  "new-version-id": ["AWSCURRENT"],
  "old-version-id": ["AWSPREVIOUS"],
  "older-version": []
}
```

## Troubleshooting

### Lambda doesn't execute

**Check**:
1. Secrets Manager rotation is configured: `aws secretsmanager describe-secret --secret-id anpr/database`
2. Lambda function exists: `aws lambda get-function --function-name anpr-secrets-rotation`
3. Lambda has permission: check `aws_lambda_permission.rotation_trigger` in Terraform

### Rotation fails at "test" step

**Causes**:
- Lambda security group doesn't allow egress to RDS
- RDS instance in maintenance window
- Password contains forbidden characters

**Check**:
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/anpr-secrets-rotation \
  --filter-pattern "ERROR"
```

### RDS password wasn't updated

**Causes**:
- Lambda role lacks `rds:ModifyDBInstance` permission
- RDS instance is read-replica or in read-only mode

**Check**:
```bash
aws iam get-role-policy \
  --role-name anpr-rotation-lambda-role \
  --policy-name anpr-rotation-lambda-rds
```

## Compliance

### SOC 2 Type II
- ✓ Automated rotation on fixed schedule
- ✓ Audit trail in CloudWatch Logs
- ✓ Encryption in transit (TLS)
- ✓ Encryption at rest (KMS)
- ✓ Access control (IAM roles)

### PCI-DSS v3.2 (8.2.3, 8.2.4)
- ✓ Password rotation every 30 days (< 90-day requirement)
- ✓ Passwords encrypted at rest (KMS)
- ✓ Passwords not stored in code
- ✓ Rotation tool audit logging

### AWS Well-Architected Framework
- **Security**: Least-privilege IAM, encryption, secrets management
- **Reliability**: Retry logic, exponential backoff, alarms
- **Operational Excellence**: Audit logging, CloudWatch monitoring
- **Performance**: VPC-native, no external API calls
- **Cost Optimization**: Lambda on-demand pricing, minimal resource usage

## Known Limitations

1. **Single RDS instance per module**: Each module rotates one RDS instance
   - Solution: Instantiate multiple modules for multiple instances

2. **PostgreSQL only**: Lambda hardcoded for PostgreSQL
   - Solution: Fork and adapt for MySQL, Oracle, etc.

3. **Master user only**: Rotates only the master user password
   - Solution: Create additional Lambda functions for application users

## Future Enhancements

1. Multi-RDS instance rotation (single Lambda with loop)
2. Custom character sets for password generation
3. Rotation notifications (Slack, email)
4. Rollback automation on failure
5. Support for MySQL/Oracle/SQL Server

## References

- [AWS Secrets Manager Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html)
- [RDS Security](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html)
- [Lambda in VPC](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)
- [Operational Guide](../../SECRETS_ROTATION.md)
