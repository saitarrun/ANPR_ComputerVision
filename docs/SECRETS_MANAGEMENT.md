# Terraform Secrets Management

This document outlines how secrets are managed in Terraform for the ANPR infrastructure.

## Principle: Never Hardcode Secrets in Terraform

Secrets (database passwords, API keys, encryption keys) are **never** hardcoded in:
- `terraform.tfvars` files
- `.tf` configuration files
- Git history

Instead, secrets are retrieved at runtime from AWS Secrets Manager.

## Architecture

### For Development/Staging

Secrets are injected via GitHub Actions → Terraform Variables:

```hcl
# terraform/variables.tf
variable "database_password" {
  description = "RDS master password (from GitHub Secrets or AWS Secrets Manager)"
  type        = string
  sensitive   = true
  # No default value; must be provided at plan/apply time
}
```

When running locally:
```bash
terraform plan -var="database_password=$(aws secretsmanager get-secret-value --secret-id anpr/dev/db-password --query 'SecretString' --output text)"
```

### For Production

Secrets are retrieved from AWS Secrets Manager using Terraform data sources:

```hcl
# terraform/main.tf
data "aws_secretsmanager_secret_version" "db_password" {
  secret_id = "anpr/prod/database-password"
}

resource "aws_db_instance" "rds" {
  # ...
  master_user_password = data.aws_secretsmanager_secret_version.db_password.secret_string
}
```

## Setup Instructions

### 1. Create Secrets in AWS Secrets Manager

```bash
# Development
aws secretsmanager create-secret \
  --name anpr/dev/database-password \
  --secret-string "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  --region us-east-1

aws secretsmanager create-secret \
  --name anpr/dev/jwt-secret \
  --secret-string "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  --region us-east-1

# Production
aws secretsmanager create-secret \
  --name anpr/prod/database-password \
  --secret-string "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  --region us-east-1

aws secretsmanager create-secret \
  --name anpr/prod/jwt-secret \
  --secret-string "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  --region us-east-1
```

### 2. Grant Terraform IAM Role Access

Ensure the Terraform execution role has permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:anpr/*"
    }
  ]
}
```

### 3. Configure Terraform Backend State Encryption

The Terraform state file contains sensitive values. Use S3 encryption:

```hcl
# terraform/backend.tf
terraform {
  backend "s3" {
    bucket         = "anpr-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}
```

Enable versioning and restrict access to the state bucket.

## Local Development

When developing locally:

1. **Store secrets in AWS Secrets Manager** (not local files)
2. **Never use `terraform.tfvars.local`** with actual passwords
3. **Use environment variables**:
   ```bash
   export TF_VAR_database_password=$(aws secretsmanager get-secret-value --secret-id anpr/dev/database-password --query 'SecretString' --output text)
   terraform plan
   ```

4. **Or use a wrapper script**:
   ```bash
   ./scripts/tf-plan.sh dev
   ```

## CI/CD Integration (GitHub Actions)

In `.github/workflows/terraform-apply.yml`:

```yaml
- name: Terraform Apply
  env:
    TF_VAR_database_password: ${{ secrets.TERRAFORM_DB_PASSWORD }}
    TF_VAR_jwt_secret: ${{ secrets.TERRAFORM_JWT_SECRET }}
  run: |
    terraform plan -out=tfplan
    terraform apply tfplan
```

## Best Practices

✓ **Do**:
- Use AWS Secrets Manager for all secrets
- Encrypt Terraform state files
- Rotate secrets regularly
- Enable MFA Delete on state bucket
- Audit secret access via CloudTrail

✗ **Don't**:
- Commit `terraform.tfvars` with actual values
- Use `terraform output` to display secrets
- Store unencrypted state files locally
- Share AWS credentials in chat/email

## Validation

Scan Terraform files for hardcoded secrets:

```bash
# Using tfsec
tfsec . --minimum-severity WARNING

# Using checkov
checkov -d terraform --check CKV_AWS_98
```

## Troubleshooting

### "Error: Error reading secret"

1. Verify the secret exists: `aws secretsmanager describe-secret --secret-id anpr/dev/database-password`
2. Verify IAM permissions: Check the Terraform role has `secretsmanager:GetSecretValue`
3. Verify region: Ensure the secret and Terraform are in the same region

### "Error: Error writing RDS instance"

1. Check database password length (must be 8+ characters)
2. Verify special characters are properly escaped in the secret
3. Check RDS parameter group allows the password characters

## Further Reading

- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
- [Terraform Sensitive Data](https://www.terraform.io/language/state/sensitive-data)
- [HashiCorp: Secrets Store Pattern](https://www.terraform.io/language/values/variables#sensitive)
