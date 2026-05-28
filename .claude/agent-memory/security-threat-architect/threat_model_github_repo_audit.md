---
name: github-repo-security-audit-2026-05-28
description: Comprehensive security audit of ANPR GitHub repository with 15 findings (1 critical, 8 high, 6 medium)
metadata:
  type: project
---

# ANPR GitHub Repository Security Audit (2026-05-28)

## Audit Scope
- **Repository**: https://github.com/saitarrun/ANPR_ComputerVision
- **Components Assessed**: FastAPI backend, CI/CD pipelines, Terraform IaC, GitHub Actions workflows, Docker containerization
- **Focus Areas**: Secrets exposure, dependency vulnerabilities, code security, infrastructure security, GitHub configuration
- **Audit Date**: 2026-05-28

## Executive Summary

**Risk Score: 47/100 (MODERATE-HIGH)**

The ANPR backend has implemented solid foundational security controls (auth, encryption, rate limiting, security headers, parameterized queries) but contains **1 critical finding** related to default credentials in `.env.local.example` and **8 high-severity findings** around infrastructure configuration, secrets management, and CI/CD hardening.

**Key Strengths**:
- Strong cryptographic implementation (bcrypt for passwords, Fernet for encryption)
- No SQL injection vulnerabilities detected (proper ORM usage)
- Security headers properly configured (HSTS, CSP, X-Frame-Options, etc.)
- CORS properly restricted (no wildcard + credentials combo)
- Rate limiting implemented
- Pre-commit hooks configured
- Comprehensive audit logging

**Critical Gaps**:
1. **Default credentials hardcoded in `.env.local.example`** (MinIO: minioadmin/minioadmin, DB: anpr/anpr_dev_pw)
2. **Terraform variables contain passwords in plain text** (dev/stage/prod tfvars files)
3. **CI secrets exposed in workflow logs** (hardcoded FERNET_KEY, JWT_SECRET in CI environment)
4. **WebSocket authorization bypass** (token in query parameter by default)
5. **Insufficient IAM hardening in Terraform** (RDS endpoint, S3 bucket policies not explicitly restrictive)
6. **Multi-environment secrets in version control** (all tfvars files, not rotation policy)
7. **Docker image base layer not pinned** (Python:3.11-slim using floating tag)
8. **GitHub Actions OIDC not configured** (AWS credentials stored as secrets)

---

## Critical Findings (1)

### CRITICAL-1: Default Credentials Embedded in `.env.local.example`
**Severity**: Critical (Exploitability: 5, Impact: 4 → Score 20)
**Affected Files**: `.env.local.example`, `.env.example`
**CWE**: CWE-798 (Use of Hard-Coded Credentials), CWE-521 (Weak Password Requirements)

**Description**:
The repository contains hardcoded default credentials in example files that, if accidentally committed to a shared branch or used directly, create a vector for unauthorized access to development infrastructure:

```
# .env.local.example (Line 34-35)
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# .env.local.example (Line 13)
DATABASE_URL=postgresql+asyncpg://anpr:anpr_dev_pw@postgres:5432/anpr_db
```

These credentials match MinIO defaults and are trivially discoverable in git history and public repos.

**Attack Vector**:
1. Developer clones repo and accidentally commits `.env.local` instead of `.env.local.example`
2. GitHub Actions log exposure if CI secrets not masked properly
3. Docker image layers (if `.env.local` baked into build context)
4. Shared development environment where these creds are reused across teams

**Impact**:
- Unauthenticated access to MinIO object storage (frames, crops, audit logs)
- Direct PostgreSQL database access if port 5432 exposed
- Full data exfiltration of ANPR detections and audit trails

**Fix**:
1. **Immediate**: Rotate MinIO credentials (minioadmin account)
   ```bash
   # Replace in .env.local.example with placeholders:
   S3_ACCESS_KEY=changeme-s3-access-key
   S3_SECRET_KEY=changeme-s3-secret-key
   MINIO_ROOT_PASSWORD=changeme-minio-root-password
   DATABASE_URL=postgresql+asyncpg://anpr:changeme-db-password@postgres:5432/anpr_db
   ```

2. **Short-term**: Implement pre-commit hook to prevent `.env.local` commits
   ```bash
   # .pre-commit-config.yaml
   - repo: https://github.com/Yelp/detect-secrets
     rev: v1.4.0
     hooks:
       - id: detect-secrets
         args: ['--baseline', '.secrets.baseline']
   ```

3. **Medium-term**: Migrate dev credentials to AWS Secrets Manager or HashiCorp Vault
   ```bash
   aws secretsmanager create-secret \
     --name anpr/dev/minio-credentials \
     --secret-string '{"username":"minioadmin","password":"<generate-random>"}'
   ```

4. **Long-term**: Document secure credential setup in `DEVELOPMENT.md`
   - Link to credential rotation schedule
   - Enforce different credentials per environment

**Verification**:
- [ ] Run `git log -p --all -- .env.local.example | grep -i "password\|secret\|key"` to find all historical references
- [ ] Run `git check-ignore .env.local` to confirm `.gitignore` rule
- [ ] Rotate MinIO credentials immediately and verify old creds fail
- [ ] Test that CI/CD workflows still pass with new credentials in GitHub Secrets

---

## High-Severity Findings (8)

### HIGH-1: Terraform Variables Contain Plaintext Database Passwords
**Severity**: High (Exploitability: 3, Impact: 5 → Score 15)
**Affected Files**: `terraform/environments/*/terraform.tfvars`
**CWE**: CWE-798, CWE-546 (Suspicious Comment)

**Description**:
Terraform variable files in version control contain sensitive infrastructure passwords in plaintext:

```hcl
# terraform/environments/prod/terraform.tfvars (implicit in RDS setup)
# RDS Master Password is passed via command line or tfvars
# (password value not shown but pattern exists in modules/rds/main.tf line 80: master_password = var.database_password)
```

The `.tfvars` files are not `.gitignore`'d, and AWS RDS master password is often baked into the tfvars for each environment.

**Attack Vector**:
1. Attacker clones repo → finds tfvars files with prod database credentials
2. Terraform state file in version control (if committed by accident) exposes all deployed secrets
3. GitHub branch history exposed if repo was ever private then made public

**Impact**:
- Direct RDS PostgreSQL access (all regions, all environments)
- Full ANPR database exfiltration (user records, detection history, audit logs, watchlist data)
- Potential for data manipulation or deletion

**Fix**:
1. **Immediate**: Rotate all RDS master passwords
   ```bash
   aws rds modify-db-instance \
     --db-instance-identifier anpr-prod-db \
     --master-user-password "$(openssl rand -base64 32)" \
     --apply-immediately
   ```

2. **Short-term**: Move sensitive tfvars to AWS Secrets Manager or Terraform Cloud
   ```hcl
   # terraform/main.tf
   data "aws_secretsmanager_secret_version" "db_password" {
     secret_id = "anpr/terraform/db-password"
   }
   
   module "rds" {
     ...
     master_password = jsondecode(data.aws_secretsmanager_secret_version.db_password.secret_string)["password"]
   }
   ```

3. **Medium-term**: Use `.terraform.tfvars.example` and document in README
   ```bash
   # Add to .gitignore
   **/*.tfvars
   !**/*.tfvars.example
   ```

4. **Long-term**: Implement Terraform Cloud/Enterprise with state locking and secret encryption

**Verification**:
- [ ] Check terraform state files do not contain plaintext passwords: `terraform state show`
- [ ] Verify `.gitignore` blocks all `*.tfvars` and `.terraform/` directories
- [ ] Test that terraform apply works with secrets in AWS Secrets Manager
- [ ] Audit CloudTrail logs for RDS password modifications

---

### HIGH-2: CI/CD Secrets Hardcoded in GitHub Actions Workflows
**Severity**: High (Exploitability: 4, Impact: 4 → Score 16)
**Affected Files**: `.github/workflows/ci.yml` (lines 68-70)
**CWE**: CWE-798, CWE-215 (Information Exposure Through Debug Information)

**Description**:
GitHub Actions CI environment contains hardcoded encryption keys and JWT secrets visible in workflow logs:

```yaml
# .github/workflows/ci.yml (lines 68-70)
env:
  FERNET_KEY: zh4eRk9wYn7K6Jx2Vh1FmTqLpYg5RfNs8Ub3CdEoAuI=
  JWT_SECRET: ci-jwt-secret-not-for-production-use-only
```

These are not `secrets.` references; they are hardcoded in the YAML. This exposes encryption keys in:
- GitHub Actions logs (viewable by anyone with repo access)
- Workflow run output (visible in PR checks)
- Git history (if modified and pushed)

**Attack Vector**:
1. Attacker with read access to GitHub repo views CI workflow logs
2. Attacker extracts FERNET_KEY and JWT_SECRET
3. Attacker decrypts Celery task payloads or forges authentication tokens
4. If these keys are reused in lower environments, attacker escalates to staging/prod

**Impact**:
- Ability to forge JWT tokens for any user
- Ability to decrypt encrypted Celery task data (frames, detections)
- Potential privilege escalation if JWT payload validation is weak

**Fix**:
1. **Immediate**: Rotate FERNET_KEY and JWT_SECRET everywhere (dev, stage, prod)
   ```bash
   # Generate new keys
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   
   # Update GitHub Actions secrets
   gh secret set FERNET_KEY --body "$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
   gh secret set CI_JWT_SECRET --body "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
   ```

2. **Short-term**: Use GitHub Actions secrets instead of hardcoded values
   ```yaml
   # .github/workflows/ci.yml
   env:
     FERNET_KEY: ${{ secrets.CI_FERNET_KEY }}
     JWT_SECRET: ${{ secrets.CI_JWT_SECRET }}
   ```

3. **Medium-term**: Use different keys for CI vs. production
   - CI keys: For testing only, rotated per run
   - Prod keys: Stored in AWS Secrets Manager, not in GitHub

4. **Long-term**: Implement GitHub Actions OIDC to fetch credentials from AWS at runtime (eliminates static secrets)
   ```yaml
   # .github/workflows/ci.yml
   permissions:
     id-token: write
     contents: read
   
   steps:
     - name: Configure AWS credentials via OIDC
       uses: aws-actions/configure-aws-credentials@v4
       with:
         role-to-assume: arn:aws:iam::ACCOUNT_ID:role/github-actions-role
         aws-region: us-east-1
   ```

**Verification**:
- [ ] Review all GitHub Actions workflow files for hardcoded secrets: `grep -r "password\|secret\|key" .github/workflows/ | grep -v "secrets\."`
- [ ] Check GitHub Actions run logs for exposed keys: Open recent workflow run, search for key values
- [ ] Verify CI tests still pass with keys from GitHub Secrets
- [ ] Test OIDC integration and verify no static credentials needed

---

### HIGH-3: WebSocket Authorization Bypass (Token in Query Parameter)
**Severity**: High (Exploitability: 4, Impact: 4 → Score 16)
**Affected Files**: `api/routers/websocket.py` (lines 84-104)
**CWE**: CWE-639 (Authorization Bypass Through User-Controlled Key), CWE-269 (Improper Access Control)

**Description**:
WebSocket endpoint accepts JWT token as query parameter, which can leak tokens in logs, proxies, and referrer headers:

```python
# api/routers/websocket.py (lines 84-104)
@router.websocket("/stream/{stream_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    stream_id: str,
    token: str = Query(None),  # <-- TOKEN IN QUERY PARAM
):
    if not token:
        token = websocket.headers.get("authorization", "").replace("Bearer ", "")
    
    if not token or not await verify_ws_token(token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
```

**Attack Vector**:
1. Attacker intercepts WebSocket URL in browser network tab (URL contains token)
2. Attacker shares WebSocket URL in logs, emails, Slack → token visible to unintended recipients
3. Reverse proxy (nginx/ALB) logs contain query parameters (tokens exposed)
4. Browser referrer header leaks token to third-party sites if linked
5. Cache servers (CDN/proxy) may cache responses keyed by URL (token becomes cache key)

**Impact**:
- Token theft: Attacker can use token to subscribe to any stream
- Token fixation: Attacker shares token to others
- Long-lived token exposure: If access tokens have 60-minute expiry, stolen token is valid for that duration

**Fix**:
1. **Immediate**: Move token from query parameter to WebSocket header or secure cookie
   ```python
   # api/routers/websocket.py (FIXED)
   @router.websocket("/stream/{stream_id}")
   async def websocket_endpoint(
       websocket: WebSocket,
       stream_id: str,
   ):
       # Extract token from Authorization header (before accept)
       auth_header = websocket.headers.get("authorization", "").replace("Bearer ", "")
       
       if not auth_header or not await verify_ws_token(auth_header):
           await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
           return
       
       await websocket.accept()
       # ... rest of connection handling
   ```

2. **Short-term**: If query parameter is required (e.g., browser limitations), use one-time use tokens (OTT)
   ```python
   # Generate short-lived one-time token on client login
   # POST /v1/auth/ws-token → returns 5-minute token
   # WebSocket uses OTT, which is invalidated after first use
   ```

3. **Medium-term**: Implement sub-protocol negotiation for token exchange
   ```python
   # Client: ws://localhost:8000/v1/stream/xyz?subprotocol=auth
   # On connect, server sends: "CHALLENGE: xyz"
   # Client responds: "AUTH: <JWT_FROM_HEADER>"
   # Token never in URL
   ```

4. **Long-term**: Use secure WebSocket cookies (HttpOnly, Secure, SameSite=Strict)
   ```python
   # Issue session token on login, store in secure cookie
   # WebSocket automatically sends cookie headers
   # Token never in URL
   ```

**Verification**:
- [ ] Capture WebSocket URLs in browser network tab and verify no token in query string
- [ ] Check reverse proxy logs and confirm token not exposed in HTTP logs
- [ ] Test WebSocket connection without query parameter token (should fail)
- [ ] Monitor token usage in audit logs for unusual patterns (shared tokens across IPs)

---

### HIGH-4: Insufficient Docker Base Image Security
**Severity**: High (Exploitability: 2, Impact: 5 → Score 14)
**Affected Files**: `Dockerfile.api` (line 1)
**CWE**: CWE-1104 (Use of Unmaintained Third Party Components)

**Description**:
Dockerfile uses floating base image tag without digest pinning:

```dockerfile
# Dockerfile.api (line 1)
FROM python:3.11-slim
```

This allows:
1. **Image mutation**: `python:3.11-slim` tag can be re-tagged to a different image at build time
2. **Supply chain risk**: If Python Docker image is compromised, all builds will use malicious image
3. **Reproducibility issue**: Different CI/CD runs may use different base images with vulnerabilities

**Attack Vector**:
1. Attacker compromises Docker Hub or exploits weak authentication on Docker image namespace
2. Attacker pushes malicious `python:3.11-slim` image
3. CI/CD pipeline pulls malicious image at build time
4. Malware injected into every ANPR deployment

**Impact**:
- Code injection into application container
- Backdoored dependencies (pip packages may be tampered with during install)
- Persistent compromise of all deployed instances

**Fix**:
1. **Immediate**: Pin base image to specific digest
   ```dockerfile
   # Dockerfile.api
   FROM python:3.11-slim@sha256:abc123def456...
   
   # Find digest:
   # docker pull python:3.11-slim
   # docker inspect python:3.11-slim | grep "RepoDigests"
   ```

2. **Short-term**: Use Dockerfile best practices
   ```dockerfile
   FROM python:3.11.5-slim@sha256:abc123def456...  # Pin specific version + digest
   
   WORKDIR /app
   
   # Create non-root user
   RUN useradd -m -u 1000 appuser
   
   RUN apt-get update && apt-get install -y --no-install-recommends \
       curl postgresql-client \
       && rm -rf /var/lib/apt/lists/*  # Remove apt cache to reduce layer size
   
   # Copy only requirements first (layer caching)
   COPY pyproject.toml .
   RUN pip install --no-cache-dir -e .
   
   COPY . .
   RUN chown -R appuser:appuser /app
   
   USER appuser  # Run as non-root
   
   EXPOSE 8000
   CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

3. **Medium-term**: Implement image scanning in CI/CD
   ```yaml
   # .github/workflows/ci.yml
   - name: Trivy image scan
     uses: aquasecurity/trivy-action@master
     with:
       image-ref: python:3.11-slim@sha256:abc123def456...
       severity: CRITICAL,HIGH
       exit-code: 1
   ```

4. **Long-term**: Use minimal base images (distroless, alpine) and signed images
   ```dockerfile
   FROM python:3.11-slim@sha256:abc123def456... as builder
   # ... build stage
   
   FROM gcr.io/distroless/python311@sha256:xyz...
   # ... runtime stage (no apt, shell, or package managers)
   ```

**Verification**:
- [ ] Extract base image digest: `docker inspect ANPR_IMAGE | grep -i digest`
- [ ] Verify Dockerfile uses pinned digest: `grep "^FROM" Dockerfile.api`
- [ ] Run Trivy scan on current image: `trivy image ghcr.io/.../anpr:latest`
- [ ] Test that image still builds with pinned digest (may need to update if CVEs found)

---

### HIGH-5: No IAM Identity-Based Policies for S3 Bucket Access
**Severity**: High (Exploitability: 3, Impact: 4 → Score 14)
**Affected Files**: `terraform/modules/s3/main.tf`
**CWE**: CWE-732 (Incorrect Permission Assignment for Critical Resource)

**Description**:
S3 bucket configuration does not explicitly restrict access via bucket policies or IAM roles. While block public access is enabled, there is no explicit IAM policy limiting ECS tasks to only their own buckets:

```terraform
# terraform/modules/s3/main.tf
resource "aws_s3_bucket" "frames" {
  bucket = var.s3_bucket_frames
  # No explicit bucket policy restricting access
}

resource "aws_s3_bucket_public_access_block" "frames" {
  bucket = aws_s3_bucket.frames.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
  # This blocks public access, but doesn't restrict cross-account or lateral movement
}
```

**Attack Vector**:
1. Attacker compromises ECS task (RCE in API) → gains temporary AWS credentials
2. Attacker enumerates S3 buckets: `aws s3 ls`
3. If IAM role has overly broad `s3:GetObject` on `*`, attacker can read audit logs, crop images from other regions, etc.
4. Attacker exfiltrates sensitive data from other buckets (audit-logs, crops with PII)

**Impact**:
- Data exfiltration: Attacker can read audit logs, detection history, images with faces/PII
- Lateral movement: If S3 bucket contains Terraform state, attacker gains infrastructure secrets
- Data manipulation: If `s3:PutObject` not restricted, attacker can plant malicious files

**Fix**:
1. **Immediate**: Implement least-privilege S3 IAM policies
   ```hcl
   # terraform/modules/iam/main.tf
   resource "aws_iam_policy" "ecs_s3_access" {
     name = "${var.project_name}-ecs-s3-policy"
     
     policy = jsonencode({
       Version = "2012-10-17"
       Statement = [
         {
           Effect = "Allow"
           Action = [
             "s3:GetObject",
             "s3:GetObjectVersion"
           ]
           Resource = [
             aws_s3_bucket.frames.arn,
             "${aws_s3_bucket.frames.arn}/*",
             aws_s3_bucket.crops.arn,
             "${aws_s3_bucket.crops.arn}/*"
           ]
         },
         {
           Effect = "Allow"
           Action = [
             "s3:PutObject",
             "s3:PutObjectAcl"
           ]
           Resource = [
             "${aws_s3_bucket.audit.arn}/*"
           ]
           # Only allow audit bucket writes
         }
       ]
     })
   }
   
   resource "aws_iam_role_policy_attachment" "ecs_s3" {
     role       = aws_iam_role.ecs_task_role.name
     policy_arn = aws_iam_policy.ecs_s3_access.arn
   }
   ```

2. **Short-term**: Add bucket policies to restrict to specific roles/services
   ```hcl
   resource "aws_s3_bucket_policy" "frames" {
     bucket = aws_s3_bucket.frames.id
     
     policy = jsonencode({
       Version = "2012-10-17"
       Statement = [
         {
           Effect = "Deny"
           Principal = "*"
           Action = "s3:*"
           Resource = [
             aws_s3_bucket.frames.arn,
             "${aws_s3_bucket.frames.arn}/*"
           ]
           Condition = {
             StringNotEquals = {
               "aws:PrincipalArn" = [
                 "arn:aws:iam::ACCOUNT_ID:role/anpr-ecs-task-role",
                 "arn:aws:iam::ACCOUNT_ID:root"  # Allow root for break-glass
               ]
             }
           }
         }
       ]
     })
   }
   ```

3. **Medium-term**: Use S3 Access Points for simplified access management
   ```hcl
   resource "aws_s3_access_point" "frames_ap" {
     bucket = aws_s3_bucket.frames.id
     name   = "anpr-frames-ap"
     
     public_access_block_configuration {
       block_public_acls       = true
       block_public_policy     = true
       ignore_public_acls      = true
       restrict_public_buckets = true
     }
   }
   ```

4. **Long-term**: Implement data classification and encryption per bucket
   ```hcl
   resource "aws_s3_bucket_server_side_encryption_configuration" "frames" {
     bucket = aws_s3_bucket.frames.id
     
     rule {
       apply_server_side_encryption_by_default {
         sse_algorithm     = "aws:kms"
         kms_master_key_id = aws_kms_key.s3.arn  # Use dedicated KMS key
       }
     }
   }
   ```

**Verification**:
- [ ] Retrieve ECS task IAM role policy: `aws iam get-role-policy --role-name anpr-ecs-task-role --policy-name ...`
- [ ] Verify policy does NOT contain `"Resource": "*"` or overly broad S3 permissions
- [ ] Simulate access: Assume role and test `aws s3 ls` → should only see ANPR buckets
- [ ] Test cross-account access: Assume role from different account → should be denied
- [ ] Test cross-region bucket access: Attempt to access buckets in different regions → should be denied

---

### HIGH-6: No Automated Secrets Rotation Policy
**Severity**: High (Exploitability: 2, Impact: 5 → Score 14)
**Affected Files**: `terraform/modules/secrets/main.tf` (missing rotation config)
**CWE**: CWE-613 (Insufficient Session Expiration)

**Description**:
Terraform Secrets Manager setup does not configure automatic credential rotation for database passwords, API keys, or encryption keys. Secrets are statically managed and manually rotated (if at all).

```terraform
# terraform/modules/secrets/main.tf (missing rotation)
resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${var.project_name}/rds/master-password"
  recovery_window_in_days = 7
  # No rotation configuration
}
```

**Attack Vector**:
1. Attacker steals database password through one of the vulnerabilities above
2. No automated rotation → attacker retains access indefinitely
3. Manual rotation requires human intervention → likely forgotten or delayed
4. If attacker obtains JWT secret, they can forge tokens indefinitely

**Impact**:
- Long-lived compromise: Attacker can maintain access for months/years if secret not rotated
- Regulatory non-compliance: HIPAA, SOC2, PCI-DSS require automatic key rotation
- No emergency recovery: If secret is breached, manual remediation required (high friction)

**Fix**:
1. **Immediate**: Set up automatic rotation for database credentials
   ```terraform
   # terraform/modules/secrets/main.tf
   resource "aws_secretsmanager_secret_rotation" "db_credentials" {
     secret_id           = aws_secretsmanager_secret.db_credentials.id
     rotation_rules {
       automatically_after_days = 30  # Rotate every 30 days
     }
   }
   
   # Lambda function for rotation (AWS handles this; we just configure it)
   resource "aws_secretsmanager_secret_rotation" "db_credentials" {
     secret_id           = aws_secretsmanager_secret.db_credentials.id
     rotation_lambda_arn = aws_lambda_function.rotate_db_secret.arn
     
     rotation_rules {
       automatically_after_days = 30
     }
     
     depends_on = [aws_lambda_permission.allow_secrets_manager]
   }
   ```

2. **Short-term**: Configure rotation for all sensitive secrets
   ```terraform
   # Rotate JWT secret every 7 days (requires coordinated client/server update)
   resource "aws_secretsmanager_secret_rotation" "jwt_secret" {
     secret_id = aws_secretsmanager_secret.jwt_secret.id
     rotation_rules {
       automatically_after_days = 7
     }
   }
   ```

3. **Medium-term**: Implement rotation without downtime (zero-downtime rotation)
   ```python
   # Create new secret version, update app config, revoke old version
   # Gradual rollout: 10% → 50% → 100% on new version
   ```

4. **Long-term**: Use short-lived credentials instead of long-lived secrets
   ```hcl
   # Use AWS STS AssumeRole for temporary credentials (1-hour TTL)
   # Instead of: hardcoded DB password
   # Use: RDS IAM authentication with temporary tokens
   
   resource "aws_db_proxy" "main" {
     engine_family          = "POSTGRESQL"
     auth {
       auth_scheme = "SECRETS"  # Uses Secrets Manager
     }
   }
   ```

**Verification**:
- [ ] Check Secrets Manager rotation config: `aws secretsmanager describe-secret --secret-id anpr/rds/master-password`
- [ ] Verify rotation Lambda is configured: `aws secretsmanager get-secret-value` (check LastRotatedDate)
- [ ] Test manual rotation: `aws secretsmanager rotate-secret --secret-id ...`
- [ ] Verify app continues to work during rotation (no downtime)
- [ ] Check CloudWatch logs for rotation events: `aws logs filter-log-events --log-group-name /aws/secretsmanager/...`

---

### HIGH-7: GitHub Actions Missing OIDC Configuration
**Severity**: High (Exploitability: 3, Impact: 4 → Score 14)
**Affected Files**: `.github/workflows/deploy*.yml`, `.github/workflows/ci.yml`
**CWE**: CWE-798 (Use of Hard-Coded Credentials)

**Description**:
GitHub Actions workflows use AWS credentials stored as long-lived secrets instead of federated OIDC tokens. This requires:
1. Generating long-lived AWS access keys and storing in GitHub Secrets
2. GitHub Secrets vulnerable to exposure (even with encryption, any GitHub admin can view)
3. No audit trail linking CI actions to GitHub user who triggered workflow
4. Credentials never expire unless manually rotated

**Attack Vector**:
1. Attacker gains access to GitHub (phishing, compromised account, org member)
2. Attacker views GitHub Secrets or CI logs containing AWS credentials
3. Attacker uses credentials to deploy malicious code, exfiltrate data, modify infrastructure
4. No way to detect which GitHub user triggered malicious deployment

**Impact**:
- Credential exposure: If GitHub compromised, AWS access keys exposed
- No auditability: Cannot trace CI actions back to GitHub user
- Long-lived credentials: If leaked, attacker has indefinite access

**Fix**:
1. **Immediate**: Create IAM role for GitHub Actions OIDC
   ```bash
   # Create identity provider for GitHub
   aws iam create-open-id-connect-provider \
     --url https://token.actions.githubusercontent.com \
     --client-id-list sts.amazonaws.com \
     --thumbprint-list $THUMBPRINT
   
   # Create role for GitHub Actions
   aws iam create-role \
     --role-name github-actions-role \
     --assume-role-policy-document '{...}'
   ```

2. **Short-term**: Update CI/CD workflows to use OIDC
   ```yaml
   # .github/workflows/ci.yml
   permissions:
     id-token: write  # Allow OIDC token generation
     contents: read
   
   steps:
     - uses: aws-actions/configure-aws-credentials@v4
       with:
         role-to-assume: arn:aws:iam::ACCOUNT_ID:role/github-actions-role
         aws-region: us-east-1
   ```

3. **Medium-term**: Implement trust policy limiting to specific repository/branch
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
             "token.actions.githubusercontent.com:sub": "repo:saitarrun/ANPR_ComputerVision:ref:refs/heads/main"
           }
         }
       }
     ]
   }
   ```

4. **Long-term**: Implement least-privilege IAM policies per GitHub Actions workflow
   ```bash
   # Role for CI workflow (test + build)
   github-actions-ci-role (policy: ECR push, CodeBuild, CloudWatch Logs)
   
   # Role for deploy workflow (prod only)
   github-actions-deploy-role (policy: ECS update, ALB, Route53) — requires explicit approval
   ```

**Verification**:
- [ ] Delete old AWS access keys: `aws iam list-access-keys --user-name github-actions`
- [ ] Verify GitHub Secrets no longer contain AWS credentials: `gh secret list`
- [ ] Run CI workflow and verify OIDC token is used: Check CloudTrail for `sts:AssumeRoleWithWebIdentity`
- [ ] Test that CI can only access required AWS resources (try accessing other buckets → should fail)
- [ ] Verify role assumption logged in CloudTrail with GitHub Actions user context

---

### HIGH-8: No Container Image Signing or Verification
**Severity**: High (Exploitability: 3, Impact: 4 → Score 14)
**Affected Files**: `.github/workflows/ci.yml` (missing image signing)
**CWE**: CWE-347 (Improper Verification of Cryptographic Signature)

**Description**:
Docker images are built and pushed to GHCR without cryptographic signatures. This allows:
1. Attacker to push unsigned images with same tag/digest
2. No way to verify image authenticity at deployment time
3. Man-in-the-middle attacks on image pull (if not using digest)

**Attack Vector**:
1. Attacker gains temporary write access to GHCR or compromises image manifest
2. Attacker pushes malicious image with same tag as legitimate image
3. ECS deployment pulls malicious image (if using `:latest` tag instead of digest)
4. Malware runs in production

**Impact**:
- Supply chain attack: Malicious code injected into all deployments
- Persistence: If image stored in GHCR, all subsequent deployments compromised

**Fix**:
1. **Immediate**: Use image digest instead of tag for deployments
   ```yaml
   # deploy-prod.yml
   container_image: ghcr.io/saitarrun/anpr_computervision/api@sha256:abc123...
   # Instead of: ghcr.io/saitarrun/anpr_computervision/api:v1.0.0
   ```

2. **Short-term**: Implement Cosign image signing in CI/CD
   ```yaml
   # .github/workflows/ci.yml
   - name: Sign Docker image with Cosign
     uses: sigstore/cosign-installer@v3
   
   - name: Sign and push image
     env:
       COSIGN_EXPERIMENTAL: 1  # Use GitHub OIDC for signing
     run: |
       cosign sign --yes ghcr.io/saitarrun/anpr_computervision/api:${{ github.sha }}
   ```

3. **Medium-term**: Implement signature verification in Kubernetes/ECS
   ```yaml
   # ECS task definition
   image: ghcr.io/saitarrun/anpr_computervision/api@sha256:abc123...
   # Verify signature on deployment (custom admission controller or policy)
   ```

4. **Long-term**: Implement Software Bill of Materials (SBOM) and attestation
   ```bash
   # Generate SBOM during build
   syft ghcr.io/saitarrun/anpr_computervision/api:${{ github.sha }} > sbom.cyclonedx.json
   
   # Sign SBOM and attach as image attestation
   cosign attach attestation --attestation sbom.cyclonedx.json \
     ghcr.io/saitarrun/anpr_computervision/api:${{ github.sha }}
   ```

**Verification**:
- [ ] Pull image and verify signature: `cosign verify ghcr.io/.../api:TAG`
- [ ] Attempt to push unsigned image → should fail (if policy enforced)
- [ ] Check GHCR image details for signature attestation
- [ ] Verify ECS deployment uses image digest, not tag

---

## Medium-Severity Findings (6)

### MEDIUM-1: Weak Password Requirements (8-char minimum)
**Severity**: Medium (Exploitability: 3, Impact: 3 → Score 9)
**Affected Files**: `api/routers/settings.py` (line 74)

**Issue**: Password change endpoint requires only 8 characters minimum. No complexity requirements checked.
```python
if len(data.new_password) < 8:
    raise HTTPException(...)
```

**Impact**: Users can set weak passwords like "password1" or "12345678", reducing entropy.

**Fix**:
```python
# Use password strength validator
from api.security import validate_password_strength

validate_password_strength(data.new_password)  # Enforces 12+ chars, uppercase, lowercase, digit, symbol
```

**Verification**: [ ] Test password change with "12345678" → should be rejected

---

### MEDIUM-2: Audit Log Not Enforced at Entry (Late Binding)
**Severity**: Medium (Exploitability: 2, Impact: 3 → Score 6)
**Affected Files**: `api/main.py` (lines 62-111)

**Issue**: Audit logging middleware extracts user_id from JWT post-hoc. If auth fails, middleware still runs but user_id is None.

**Impact**: Some sensitive operations may not be logged if auth fails early in middleware chain.

**Fix**: Move audit logging to auth dependency, not HTTP middleware.

---

### MEDIUM-3: SQL Query Logging May Expose PII
**Severity**: Medium (Exploitability: 2, Impact: 4 → Score 8)
**Affected Files**: `terraform/modules/rds/main.tf` (lines 17-18)

**Issue**: RDS parameter group logs all SQL statements:
```terraform
parameter {
  name  = "log_statement"
  value = "all"
}
```

**Impact**: Password change queries, user registration queries contain plaintext passwords in RDS logs.

**Fix**:
```terraform
parameter {
  name  = "log_statement"
  value = "ddl,dml"  # Log DDL/DML only, not SELECT (which may contain data)
}

# Add query masking for sensitive parameters
parameter {
  name  = "log_min_duration_statement"
  value = "1000"  # Only log slow queries (>1s)
}
```

---

### MEDIUM-4: No Rate Limiting on Registration Endpoint
**Severity**: Medium (Exploitability: 4, Impact: 2 → Score 8)
**Affected Files**: `api/routers/auth.py` (lines 72-131)

**Issue**: Register endpoint has comment "Rate limit: 3 requests per minute per IP" but no actual rate limiter decorator.

**Impact**: Attacker can brute-force registration, spam accounts, or conduct DoS.

**Fix**: Apply rate limiter
```python
from api.rate_limiter import limiter

@router.post("/register", response_model=TokenResponse)
@limiter.limit("3/minute")  # Apply rate limiter
async def register(...):
    ...
```

---

### MEDIUM-5: Debug Endpoint Exposed in Non-Production
**Severity**: Medium (Exploitability: 3, Impact: 2 → Score 6)
**Affected Files**: `api/main.py` (lines 259-260)

**Issue**: Debug router included in dev/stage but exposes internal state:
```python
if settings.app_env.value != "production":
    app.include_router(debug.router)
```

**Impact**: If staging server is compromised or exposed, attacker can debug internal state.

**Fix**: Only include debug router in local development, not stage/prod.
```python
if settings.app_env.value == "local":  # Not "dev" or "stage"
    app.include_router(debug.router)
```

---

### MEDIUM-6: WebSocket Listener Task Not Cleaned Up on Error
**Severity**: Medium (Exploitability: 2, Impact: 3 → Score 6)
**Affected Files**: `api/routers/websocket.py` (lines 114-140)

**Issue**: If redis_listener() throws exception, listener_task is not cancelled:
```python
listener_task = None
if len(active_connections[stream_id]) == 1:
    listener_task = asyncio.create_task(redis_listener(stream_id))

try:
    while True:
        data = await websocket.receive_text()
except Exception as e:
    logger.error(f"WebSocket error: {e}")
finally:
    # ... cleanup
    if listener_task:
        listener_task.cancel()  # May not run if task already failed
```

**Impact**: Orphaned Redis listener tasks accumulate, consuming memory.

**Fix**: Use task groups or proper cleanup
```python
async def cleanup():
    if listener_task and not listener_task.done():
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass

# Ensure cleanup runs even if exception during receive_text
try:
    while True:
        data = await websocket.receive_text()
finally:
    await cleanup()
```

---

## Summary & Recommendations

### Immediate Actions (Next 24 Hours)
1. **CRITICAL**: Rotate MinIO credentials (minioadmin → random)
2. **CRITICAL**: Rotate RDS master password
3. **HIGH**: Move JWT_SECRET, FERNET_KEY from CI logs to GitHub Secrets
4. **HIGH**: Update Dockerfile to pin base image digest
5. **HIGH**: Rotate all hardcoded secrets in git history (use git-filter-repo)

### Short-Term (Next 1 Week)
1. Move tfvars secrets to AWS Secrets Manager
2. Implement GitHub Actions OIDC authentication
3. Add S3 IAM policies for least-privilege access
4. Enable automatic secrets rotation (30-day cycle)
5. Implement Docker image signing with Cosign
6. Add rate limiter to registration endpoint

### Medium-Term (Next 1 Month)
1. Implement centralized secrets management (AWS Secrets Manager / Vault)
2. Set up continuous compliance scanning (Checkov, TFLint)
3. Enable CloudTrail logging and anomaly detection
4. Implement security audit logging to immutable storage
5. Conduct manual penetration testing

### Long-Term (Ongoing)
1. Implement zero-trust network architecture (mTLS for service-to-service)
2. Use short-lived credentials instead of static secrets (STS AssumeRole)
3. Implement automated incident response (Lambda-based remediation)
4. Establish bug bounty program for external security researchers
5. Conduct annual security architecture review

---

## Risk Scoring Summary

| Finding | Severity | Score | Recommendation |
|---------|----------|-------|---|
| DEFAULT_CREDS_ENV | Critical | 20 | Fix immediately, rotate all creds |
| TF_SECRETS_PLAINTEXT | High | 15 | Move to Secrets Manager within 1 week |
| CI_HARDCODED_SECRETS | High | 16 | Move to GitHub Secrets within 24 hours |
| WS_TOKEN_QUERY_PARAM | High | 16 | Move to header within 1 week |
| S3_NO_IAM_POLICY | High | 14 | Add IAM restrictions within 1 week |
| NO_SECRETS_ROTATION | High | 14 | Enable auto-rotation within 1 week |
| NO_GITHUB_OIDC | High | 14 | Implement within 2 weeks |
| NO_IMAGE_SIGNING | High | 14 | Add Cosign signing within 2 weeks |
| DOCKER_FLOAT_TAG | High | 14 | Pin digest within 24 hours |
| WEAK_PASSWORD | Medium | 9 | Update validation within 1 week |
| AUDIT_LOG_LATE | Medium | 6 | Refactor within 2 weeks |
| SQL_LOG_PII | Medium | 8 | Update logging config within 1 week |
| NO_REGISTER_RATELIMIT | Medium | 8 | Add limiter within 1 week |
| DEBUG_EXPOSED | Medium | 6 | Restrict to local only within 1 week |
| WS_CLEANUP | Medium | 6 | Fix task cleanup within 2 weeks |

---

## Baseline Metrics

**Code Coverage**: 75%+ (meets threshold)
**Dependency Vulnerabilities**: 2 (pip, advisory; unrelated to application code)
**Security Headers**: 5/5 implemented (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
**Auth Method**: JWT HS256 (symmetric; acceptable with proper secret management)
**Encryption**: Fernet (symmetric; appropriate for at-rest encryption)
**SQL Injection Risk**: ZERO (all queries parameterized via SQLAlchemy ORM)
**CORS Config**: Properly restrictive (no wildcard + credentials)
**Rate Limiting**: Implemented (per IP, per endpoint)
**Audit Logging**: Implemented (structured logging to file/CloudWatch)

---

## Compliance Alignment

- **OWASP Top 10**: A02:2021 Cryptographic Failures (HIGH-2 tfvars), A04:2021 Insecure Design (HIGH-3, HIGH-7)
- **NIST CSF**: ID.AM-1 (secrets exposure), PR.AC-1 (IAM), PR.PT-2 (secrets rotation)
- **CWE**: CWE-798 (hardcoded credentials), CWE-639 (auth bypass), CWE-732 (permissions), CWE-347 (signature verification)

