# Security Fixes: Container & OIDC (HIGH-4, HIGH-7, HIGH-8)

## Summary
Fixed three critical supply chain and authorization security issues in Docker image and GitHub Actions workflows.

---

## HIGH-4: Docker Base Image Floating Tag → Pinned SHA256

**Status:** ✅ FIXED

### Problem
`FROM python:3.11-slim` pulls the latest version tag. If Docker Hub is compromised, malicious image could be injected into the build chain.

### Solution
Pinned to immutable SHA256 digest:
```dockerfile
FROM python:3.11-slim@sha256:a3ab0b966bc4e91546a033e22093cb840908979487a9fc0e6e38295747e49ac0
```

### Files Changed
- `/Dockerfile` (builder & runtime stages, lines 3, 28)

### Verification
```bash
docker pull python:3.11-slim
docker inspect python:3.11-slim | grep -A1 RepoDigests
```

### Maintenance
- **Monthly update cycle:** First Monday of each month, run digest refresh
- **Script:**
  ```bash
  docker pull python:3.11-slim
  DIGEST=$(docker inspect python:3.11-slim | grep -oP '(?<=sha256:)[a-f0-9]{64}' | head -1)
  sed -i "s/@sha256:[a-f0-9]{64}/@sha256:${DIGEST}/g" Dockerfile
  ```
- **Testing:** `docker build --no-cache -t anpr:test .` must succeed

---

## HIGH-8: Container Image Signing (Cosign)

**Status:** ✅ CONFIGURED (Setup Required)

### Problem
No cryptographic verification that built images are authentic and haven't been tampered with.

### Solution
Added Cosign signing to all build and deployment workflows.

### Changes Made

#### 1. Build Workflow (`.github/workflows/docker-build.yml`)
- Install Cosign v2.2.0
- Sign images after push to GHCR
- Supports keyless signing via GitHub OIDC (Sigstore)

#### 2. Deploy Workflows (`.github/workflows/deploy.yml`)
- **Staging deploy:** Verify signature before deployment (optional warn mode)
- **Prod blue-green:** Verify signature before deployment (strict fail mode)
- **Prod canary:** Verify signature before deployment (strict fail mode)

#### 3. Files Changed
- `.github/workflows/docker-build.yml` (added signing step)
- `.github/workflows/deploy.yml` (added cosign installer & verification steps)

### Setup Steps

**Option A: Keyless Signing (Recommended)**
1. No secrets required — uses GitHub OIDC token
2. Cosign automatically issues short-lived certificates from Sigstore
3. Verification uses public Sigstore infrastructure
4. Workflows already have `id-token: write` permission

**Option B: Private Key Signing (Alternative)**
1. Generate key pair:
   ```bash
   cosign generate-key-pair
   # Generates cosign.key (private) and cosign.pub (public)
   ```
2. Add GitHub secret `COSIGN_PRIVATE_KEY` = contents of `cosign.key`
3. Update workflows to use `--key ${{ secrets.COSIGN_PRIVATE_KEY }}`
4. Commit `cosign.pub` to repo for verification

### Verification Commands

**Check if image is signed:**
```bash
cosign tree ghcr.io/saitarrun/ANPR_ComputerVision/anpr-backend:latest
```

**Verify signature (keyless):**
```bash
export COSIGN_EXPERIMENTAL=1
cosign verify \
  --certificate-identity-regexp ".*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/saitarrun/ANPR_ComputerVision/anpr-backend:latest
```

**Verify signature (with public key):**
```bash
cosign verify \
  --key cosign.pub \
  ghcr.io/saitarrun/ANPR_ComputerVision/anpr-backend:latest
```

### Deployment Behavior
- **Staging:** Warns if signature missing; deployment continues
- **Production:** Fails immediately if signature verification fails
- **Intent:** Catch tampering before prod; allow graceful handling in lower environments

---

## HIGH-7: GitHub Actions OIDC (Replace Static Credentials)

**Status:** ✅ ALREADY IMPLEMENTED

### Verification
Workflows are already using AWS OIDC with `aws-actions/configure-aws-credentials@v4`:

```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/GithubActionsRole
    aws-region: us-east-1
```

### Current State
- ✅ `deploy.yml` has `permissions: id-token: write` (required for OIDC)
- ✅ All 5 AWS credential usages (build, deploy-stage, deploy-prod-blue-green, deploy-prod-canary, rollback) use OIDC
- ✅ No static AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY in workflows
- ✅ AWS_ACCOUNT_ID is a simple non-sensitive constant (account number)

### How It Works
1. GitHub OIDC provider token issued to workflow
2. Exchanged for temporary STS credentials via IAM role
3. Credentials valid for ~1 hour (auto-expires)
4. No long-lived credentials stored in GitHub secrets

### What Needs to Exist in AWS
This assumes the following already exist (verify in AWS console):

```
Account: {AWS_ACCOUNT_ID}
OIDC Provider: arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com
IAM Role: GithubActionsRole
  Trust Policy includes:
    Principal: OIDC provider above
    Condition: token.actions.githubusercontent.com:sub = repo:saitarrun/ANPR_ComputerVision:*
  Permissions: ECR push, ECS deploy, ALB config (see deploy.yml actions)
```

### Verification Checklist
```bash
# 1. Check OIDC provider exists
aws iam list-open-id-connect-providers

# 2. Check role exists
aws iam get-role --role-name GithubActionsRole

# 3. Check trust policy
aws iam get-role-policy --role-name GithubActionsRole --policy-name <policy-name>

# 4. Run a workflow dispatch and check CloudTrail for AssumeRoleWithWebIdentity
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --max-results 10
```

---

## Testing Checklist

- [ ] **HIGH-4:** `docker build --no-cache -t test:pinned .` succeeds
- [ ] **HIGH-4:** `docker inspect test:pinned | grep RepoDigests` shows SHA256 digest
- [ ] **HIGH-8:** Trigger `docker-build.yml` workflow on main branch
  - Check build logs for "Signing image" steps
  - Verify image appears in GHCR
- [ ] **HIGH-8:** Run cosign verification command (see above)
- [ ] **HIGH-8:** Trigger staging deploy (manual)
  - Should attempt signature verification (warn on missing)
  - Deployment should proceed
- [ ] **HIGH-8:** Trigger prod deploy (manual)
  - Should attempt strict signature verification
  - If verification fails, deployment stops
- [ ] **HIGH-7:** Trigger any deployment workflow
  - Check CloudTrail for AssumeRoleWithWebIdentity calls
  - Verify no static credentials in logs

---

## Production Readiness

### Before Merging
- [ ] All three workflows tested in CI/CD pipeline
- [ ] Cosign public key committed if using Option B
- [ ] AWS secrets `AWS_ACCOUNT_ID` is set (non-sensitive account number)
- [ ] IAM role `GithubActionsRole` exists with correct trust policy

### Deployment
1. Merge this PR to main
2. Tag a release: `git tag v0.x.x && git push origin v0.x.x`
3. Watch workflow execution
4. Verify signatures in GHCR/ECR

### Rollout
- **No breaking changes** — existing deployments continue to work
- **Verification is additive** — staging has graceful warnings, prod fails safely

---

## References
- Cosign: https://github.com/sigstore/cosign
- Sigstore: https://www.sigstore.dev/
- AWS OIDC: https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- OCI Image Spec: https://github.com/opencontainers/image-spec
