# GitHub Secrets Configuration

This document outlines the GitHub Secrets that must be configured for CI/CD workflows to function securely.

## Required Secrets

All secrets must be set in the GitHub repository settings under **Settings → Secrets and Variables → Actions**.

### CI/CD Secrets (for testing and staging)

| Secret Name | Purpose | Example Generation | Required For |
|-------------|---------|-------------------|--------------|
| `CI_DATABASE_PASSWORD` | PostgreSQL password for test environment | `python -c "import secrets; print(secrets.token_urlsafe(32))"` | ci.yml, deploy.yml |
| `CI_FERNET_KEY` | Celery encryption key for CI tests | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | ci.yml, deploy.yml |
| `CI_JWT_SECRET` | JWT signing key for CI tests | `python -c "import secrets; print(secrets.token_urlsafe(32))"` | ci.yml, deploy.yml |
| `AWS_ACCOUNT_ID` | AWS account ID for ECR push | From AWS console | deploy.yml, deploy-staging.yml, deploy-prod.yml, rollback-prod.yml |

### Production Secrets (for staging and production deployments)

| Secret Name | Purpose | Source | Required For |
|-------------|---------|--------|--------------|
| `PROD_DATABASE_PASSWORD` | RDS master password (production) | AWS Secrets Manager | deploy-prod.yml |
| `PROD_JWT_SECRET` | JWT key for production | AWS Secrets Manager | deploy-prod.yml |
| `PROD_FERNET_KEY` | Fernet key for production | AWS Secrets Manager | deploy-prod.yml |

## Setup Instructions

### 1. Generate Test Secrets

```bash
# Generate CI_DATABASE_PASSWORD
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate CI_FERNET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate CI_JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Set Secrets in GitHub

1. Go to repository **Settings** → **Secrets and Variables** → **Actions**
2. Click **New repository secret**
3. Add each secret with the name and value from above
4. For `AWS_ACCOUNT_ID`, use your actual AWS account ID

### 3. Production Secrets (AWS Secrets Manager)

For production deployments, secrets are retrieved from AWS Secrets Manager instead of GitHub Secrets.
Ensure the following secrets exist in AWS Secrets Manager:

```
arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:anpr/prod/database-password
arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:anpr/prod/jwt-secret
arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:anpr/prod/fernet-key
```

Configure the `GithubActionsRole` IAM role to have permissions to read these secrets.

## Security Best Practices

- **Never commit secrets to version control.**
- **Rotate secrets regularly** (quarterly recommended).
- **Use unique secrets for each environment** (CI, staging, production).
- **Use AWS Secrets Manager for production** instead of GitHub Secrets.
- **Audit secret access** via CloudTrail and GitHub Audit Log.
- **Use OIDC for AWS authentication** instead of access keys (preferred).

## Validation

To verify secrets are not exposed in the codebase:

```bash
# Check for hardcoded credentials
grep -r "password\|secret\|key" .github/workflows/ | grep -v "secrets\."

# Use detect-secrets (pre-commit hook)
detect-secrets scan --baseline .secrets.baseline
```

## Troubleshooting

### "Secret not found" error in workflows

1. Verify secret name matches exactly (case-sensitive)
2. Confirm secret is set in the correct repository
3. Check that the workflow has permissions to access secrets (inherited by default)

### AWS Credential Errors

1. Verify `AWS_ACCOUNT_ID` is correct
2. Confirm `GithubActionsRole` exists in IAM
3. Check role trust relationship includes GitHub OIDC provider

## Further Reading

- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [AWS Secrets Manager Integration](https://github.com/aws-actions/configure-aws-credentials)
- [OWASP: Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
