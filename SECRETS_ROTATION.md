# Secrets Rotation: Operational Guide

## Overview

This system implements automatic RDS password rotation via AWS Secrets Manager and a Lambda function. The rotation follows AWS best practices for zero-downtime credential updates compliant with SOC 2 and PCI-DSS standards.

## Rotation Lifecycle

Secrets Manager triggers the Lambda function automatically on a 30-day schedule. The rotation executes in 4 atomic steps:

### 1. **Create** (Step 1)
- Lambda generates a new 32-character password (uppercase, lowercase, digits, special chars)
- Password is validated against RDS requirements (no `/`, `"`, `\`, `@`)
- New password stored as `AWSPENDING` version in Secrets Manager
- Existing applications continue using `AWSCURRENT` (old password)
- **Duration**: < 1 second
- **Risk**: None—no production data touched

### 2. **Set** (Step 2)
- Lambda retrieves the `AWSPENDING` secret with new password
- Calls `ModifyDBInstance` to update RDS master user password
- RDS applies password change immediately (`ApplyImmediately=true`)
- Existing connections remain valid until they need to re-authenticate
- **Duration**: 10-30 seconds (typical RDS API latency)
- **Risk**: Low—RDS accepts both old and new passwords briefly during credential propagation

### 3. **Test** (Step 3)
- Lambda retrieves the `AWSPENDING` secret
- Opens a PostgreSQL connection to RDS using the new password
- Executes `SELECT 1` to verify authentication and database access
- Closes connection
- If test fails, rotation stops (reverts to `AWSCURRENT`); no applications affected
- **Duration**: 5-10 seconds
- **Risk**: None—read-only test query, no data modified

### 4. **Finish** (Step 4)
- Lambda moves `AWSPENDING` to `AWSCURRENT` in Secrets Manager
- ECS/application containers will refresh their cached credentials on next refresh cycle
- Old version kept as `AWSPREVIOUS` for rollback (7-day retention window)
- **Duration**: < 1 second
- **Risk**: None—Secrets Manager is authoritative; cached credentials in apps gradually refresh

## Architecture

```
AWS Secrets Manager
    ↓ [rotation event every 30 days]
    ↓
Lambda Function (rotate_secret.py)
    ├─ Reads AWSCURRENT (old password)
    ├─ Generates new password → AWSPENDING
    ├─ Calls RDS ModifyDBInstance
    ├─ Tests new password
    └─ Promotes AWSPENDING → AWSCURRENT
    ↓
RDS PostgreSQL (password updated)
    ↓
ECS Application (refreshes credentials from Secrets Manager)
```

## Compliance

### SOC 2 Type II
- **Automated rotation** on fixed 30-day schedule (audit trail in CloudWatch Logs)
- **Principle of least privilege**: Lambda role restricted to specific RDS instance and secret
- **Encryption in transit**: Lambda → RDS uses SSL/TLS; Lambda → Secrets Manager uses HTTPS
- **Audit logging**: All rotation steps logged to CloudWatch with timestamps and outcomes

### PCI-DSS v3.2 (Requirement 8.2.3 & 8.2.4)
- Passwords changed at least every 90 days → **30-day schedule exceeds requirement**
- Passwords must be encrypted → **KMS encryption for secrets at rest**
- Cannot be transmitted in plaintext → **SSL/TLS only**
- Cannot be stored in code/configuration → **Secrets Manager as single source of truth**

### AWS Best Practices
- **Zero-downtime rotation**: Old and new passwords coexist briefly
- **Atomic transitions**: Version staging prevents partially-updated state
- **Idempotent operations**: Retries on transient failures (InvalidDBInstanceState)
- **Dead-letter handling**: CloudWatch alerts on any step failure

## Monitoring & Troubleshooting

### CloudWatch Logs

Rotation logs appear in `/aws/lambda/{project-name}-secrets-rotation`:

```json
{
  "timestamp": "2026-05-28T14:32:15Z",
  "level": "INFO",
  "message": "Starting rotation step 'create' for secret anpr/database with token abc-123-def"
}
```

**Log levels**:
- `INFO`: Rotation step starting/completed
- `WARNING`: Transient failures (retrying)
- `ERROR`: Fatal failures (rotation halted)

### CloudWatch Alarms

Two alarms monitor rotation health:

1. **`{project}-rotation-invocation-errors`**
   - Triggers if Lambda exits with error (step fails)
   - Sends to SNS topic → email alert
   - Action: Check logs in CloudWatch; see "Failed Rotation" section below

2. **`{project}-rotation-duration-high`**
   - Triggers if step takes > 50 seconds (timeout is 60s)
   - Indicates network latency or RDS API slowness
   - Action: Monitor RDS CPU/connections; check AWS status page

### Secrets Manager Console

View rotation history:
1. AWS Secrets Manager → `{project}/database`
2. Tab: "Rotation configuration"
3. Scroll to "Rotation history"

Each entry shows:
- Status: `Succeeded` or `Failed`
- Step: which of the 4 steps failed (if failed)
- Timestamp

## Operational Procedures

### Manual Trigger (Testing)

To force an immediate rotation (do not run during production hours):

```bash
aws secretsmanager rotate-secret \
  --secret-id anpr/database \
  --rotation-rules AutomaticallyAfterDays=30
```

Then monitor in CloudWatch Logs and check the Secrets Manager rotation history.

### Check Last Rotation Status

```bash
aws secretsmanager describe-secret \
  --secret-id anpr/database \
  --query 'RotationRules.LastRotatedDate'
```

Expected output:
```
"2026-05-28T14:30:00+00:00"
```

### View Active Password

To verify which version is currently active:

```bash
aws secretsmanager describe-secret \
  --secret-id anpr/database \
  --query 'VersionIdsToStages'
```

Expected output (after successful rotation):
```json
{
  "abc-123-def": ["AWSCURRENT"],
  "xyz-789-uvw": ["AWSPREVIOUS"],
  "old-version": []
}
```

### Application Integration

ECS tasks automatically refresh credentials from Secrets Manager. No manual restart required.

**For non-ECS workloads** (Lambda, EC2 standalone):
- Implement Secrets Manager client with caching TTL of 1 hour max
- On error accessing database, refresh credentials immediately
- Never hardcode passwords; always read from Secrets Manager

Example (Python):

```python
import boto3
import json
from botocore.exceptions import ClientError

def get_db_credentials():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    try:
        response = client.get_secret_value(SecretId='anpr/database')
        return json.loads(response['SecretString'])
    except ClientError as e:
        raise ValueError(f"Failed to retrieve secret: {e}")

# Use credentials
creds = get_db_credentials()
conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    user=creds['username'],
    password=creds['password'],
    dbname=creds.get('dbname', 'anpr')
)
```

## Failed Rotation: Troubleshooting

### Scenario 1: "test" step fails (connection error)

**Symptoms**:
- CloudWatch log shows ERROR at "test" step
- Rotation status: `Failed`
- RDS password was updated, but new one doesn't work

**Causes**:
- New password contains forbidden character (shouldn't happen, but possible bug)
- RDS security group blocks Lambda ingress on port 5432
- RDS instance unavailable or in maintenance window
- Lambda doesn't have permission to describe RDS instance

**Resolution**:
1. Check Lambda security group allows egress to RDS security group on port 5432
2. Check RDS instance status: `aws rds describe-db-instances --db-instance-identifier {id}`
3. Review Lambda execution role policy (Terraform: `aws_iam_policy.rotation_lambda_rds`)
4. Check if RDS is in maintenance window (AWS Console → RDS → Databases)

**Manual Recovery**:
```bash
# Option A: Retry the rotation (Secrets Manager will retry from "test" step)
aws secretsmanager rotate-secret --secret-id anpr/database

# Option B: Reset to known-good state (if database is locked)
# This requires manually resetting RDS password via AWS Console or CLI
aws rds modify-db-instance \
  --db-instance-identifier anpr-db \
  --master-user-password 'NewMasterPassword123!' \
  --apply-immediately

# Then update secret manually in AWS Console to avoid mismatch
```

### Scenario 2: "set" step fails (RDS API error)

**Symptoms**:
- CloudWatch log shows ERROR at "set" step (InvalidDBInstanceState)
- Rotation status: `Failed`
- RDS password unchanged

**Causes**:
- RDS instance in maintenance window or unavailable
- Another RDS operation in progress
- Insufficient Lambda IAM permissions
- RDS instance doesn't exist

**Resolution**:
1. Verify RDS instance exists: `aws rds describe-db-instances --db-instance-identifier anpr-db`
2. Check for ongoing operations: look for "Pending modifications" in RDS Console
3. Check Lambda IAM role has `rds:ModifyDBInstance` on the target instance ARN
4. Wait for maintenance window to complete, then retry

### Scenario 3: "create" step fails (Secrets Manager error)

**Symptoms**:
- CloudWatch log shows ERROR at "create" step
- Rotation status: `Failed`

**Causes**:
- Lambda doesn't have `secretsmanager:PutSecretValue` permission
- Secret doesn't exist or is deleted
- KMS key is disabled/deleted

**Resolution**:
1. Verify secret exists: `aws secretsmanager describe-secret --secret-id anpr/database`
2. Verify Lambda IAM role has Secrets Manager permissions: check Terraform `aws_iam_policy.rotation_lambda_secrets`
3. Verify KMS key status (check if rotation_lambda policy includes KMS decrypt/encrypt)
4. If KMS key disabled, enable it: `aws kms enable-key --key-id {key-id}`

### Scenario 4: Rotation stuck in "AWSPENDING" state

**Symptoms**:
- Secrets Manager shows rotation "In Progress" for > 10 minutes
- No new log entries in CloudWatch

**Causes**:
- Lambda timeout (60s exceeded)
- Lambda crashed without updating version stage
- Secrets Manager API throttled
- Network connectivity issue

**Resolution**:
1. Check Lambda logs for the last entry; note the timestamp
2. If logs show step completed but no stage update, manually fix:
   ```bash
   aws secretsmanager update-secret-version-stage \
     --secret-id anpr/database \
     --version-stage AWSCURRENT \
     --move-to-version-id {token-from-logs}
   ```
3. If logs show no completion, Lambda may have timed out or crashed
4. Retry rotation:
   ```bash
   aws secretsmanager rotate-secret --secret-id anpr/database
   ```

## Rollback Procedures

### If New Password Causes Application Outage

**Immediate action** (< 2 minutes to restore):

1. **Identify the issue**: 
   ```bash
   # Check which version is AWSCURRENT
   aws secretsmanager describe-secret --secret-id anpr/database --query 'VersionIdsToStages'
   ```

2. **Revert to previous password**:
   ```bash
   # Find AWSPREVIOUS version
   OLD_VERSION=$(aws secretsmanager describe-secret --secret-id anpr/database \
     --query "VersionIdsToStages" | grep -A1 AWSPREVIOUS | head -1)
   
   # Move AWSPREVIOUS back to AWSCURRENT
   aws secretsmanager update-secret-version-stage \
     --secret-id anpr/database \
     --version-stage AWSCURRENT \
     --move-to-version-id $OLD_VERSION
   ```

3. **Restart application pods** (they'll re-fetch old password):
   ```bash
   kubectl rollout restart deployment/anpr-api -n production
   ```

4. **Manually reset RDS password**:
   ```bash
   aws rds modify-db-instance \
     --db-instance-identifier anpr-db \
     --master-user-password 'OldPasswordFromAWSPrevious' \
     --apply-immediately
   ```

### If Entire Rotation Process Fails

1. **Identify which step failed** (check CloudWatch logs)
2. **Do NOT attempt to fix in-place**; instead, cancel and re-run:
   ```bash
   # View rotation state
   aws secretsmanager describe-secret --secret-id anpr/database
   
   # If "Rotation in progress", you may need to wait for Lambda timeout (60s)
   # or manually clean up AWSPENDING:
   aws secretsmanager update-secret-version-stage \
     --secret-id anpr/database \
     --version-stage AWSPENDING \
     --remove-from-version-id {bad-version}
   ```
3. **Fix the underlying issue** (see troubleshooting scenarios above)
4. **Retry rotation** (automated or manual)

## Security Considerations

### Password Generation

Passwords are generated using Python's `secrets` module (cryptographically secure random):
- 32 characters (exceeds RDS minimum of 8)
- Includes uppercase, lowercase, digits, and special characters
- Excludes problematic characters: `@`, `/`, `"`, `\` (to avoid SQL/shell injection risks)
- Validated before use

### Secret Isolation

Lambda has minimal permissions:
- Can read/write only to `{project}/database` secret
- Can modify only the specific RDS instance
- Cannot access other secrets, instances, or resources
- VPC security group restricts network egress to RDS and AWS API endpoints only

### Encryption

- **Secrets at rest**: KMS-encrypted in Secrets Manager
- **Secrets in transit**: 
  - Lambda → Secrets Manager: HTTPS
  - Lambda → RDS: SSL/TLS (enforced by RDS parameter `rds.force_ssl=1`)
- **Secrets in Lambda memory**: Cleared after step completes
- **Logs**: CloudWatch Logs redacts password values automatically

### Audit Trail

All rotation attempts logged:
- Who triggered (AWS service identity)
- When (timestamp)
- What step (create/set/test/finish)
- Outcome (success/failure)
- Error message (if failed)

Logs retained for 30 days; export to S3 for long-term compliance archival:

```bash
aws logs create-export-task \
  --log-group-name /aws/lambda/anpr-secrets-rotation \
  --from $(date -d '30 days ago' +%s)000 \
  --to $(date +%s)000 \
  --destination s3-bucket-name \
  --destination-prefix rotation-audit-logs/
```

## Compliance Checklist

### SOC 2 Type II
- [ ] Automated rotation configured and tested
- [ ] Rotation logs reviewed (at least monthly)
- [ ] Alarms configured and tested
- [ ] Rotation failures responded to within 24 hours
- [ ] Access to Secrets Manager and Lambda restricted to authorized personnel
- [ ] KMS key policy audited annually

### PCI-DSS v3.2
- [ ] Password rotation schedule < 90 days (30 days configured) ✓
- [ ] Passwords encrypted at rest (KMS) ✓
- [ ] Passwords transmitted securely (TLS/SSL) ✓
- [ ] Passwords not in code or configuration ✓
- [ ] Rotation tool (Lambda) has audit logging ✓
- [ ] Failed rotations investigated and resolved ✓

### ISO 27001
- [ ] Rotation policy documented (this file) ✓
- [ ] Rotation procedure tested in non-production
- [ ] Emergency rollback procedure tested
- [ ] Key personnel trained on troubleshooting

## Next Steps

1. **Deploy**: Run `terraform apply -target module.lambda_rotate`
2. **Test in dev/staging**: Manually trigger rotation, verify logs
3. **Enable SNS alerts**: Subscribe to SNS topic for rotation failure notifications
4. **Monitor**: Check CloudWatch dashboard weekly for rotation trends
5. **Annual review**: Test rollback procedure and update documentation

## References

- [AWS Secrets Manager Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html)
- [RDS Master Password Requirements](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html)
- [PostgreSQL psycopg2 Connection](https://www.psycopg.org/docs/)
- [SOC 2 Type II Compliance](https://www.aicpa.org/interestareas/informationsystemsaudit/assuranceadvisoryservices/aicpasoc2report.html)
- [PCI-DSS v3.2 Requirement 8](https://www.pcisecuritystandards.org/documents/PCI_DSS_v3-2-1.pdf)
