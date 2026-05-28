# CI/CD Pipeline Setup Guide

This document describes the complete CI/CD infrastructure for the ANPR backend.

## Overview

The pipeline implements a production-grade deployment system with these stages:

```
┌─────────────────────────────────────────────────────────────┐
│ Developer Push to main/develop                              │
└────────────────────────────┬────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  CI: Lint/Test  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Build Image   │  (all branches)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Deploy Staging │  (main only)
                    │  + Smoke Tests  │
                    └────────┬────────┘
                             │
                   ┌─────────▼─────────┐
                   │ Git Tag v*.*.* → Prod
                   │ Manual Approval   │
                   └─────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Deploy Production│
                    │ Blue-Green       │
                    │ + Monitoring     │
                    └──────────────────┘
```

## Environment Variables & Secrets

### Required GitHub Secrets

Set these in **Settings → Secrets and Variables → Actions**:

#### Container Registry
- `REGISTRY` = `ghcr.io` (GitHub Container Registry)
- Auto-authenticated via `secrets.GITHUB_TOKEN` (no additional secret needed)

#### Staging Deployment
- `STAGING_DEPLOY_HOST` = Hostname/IP of staging server
- `STAGING_DEPLOY_USER` = SSH user (e.g., `deploy`)
- `STAGING_DEPLOY_KEY` = SSH private key (PEM format) for passwordless SSH

#### Production Deployment
- `PROD_DEPLOY_HOST` = Hostname/IP of production server
- `PROD_DEPLOY_USER` = SSH user (e.g., `deploy`)
- `PROD_DEPLOY_KEY` = SSH private key (PEM format)

#### Notifications
- `SLACK_WEBHOOK_DEPLOY` = Slack webhook URL for deployment notifications
  - Format: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX`
  - Create via Slack app → Incoming Webhooks

### Environment Variables in Deployment

Create `.env.staging` and `.env.prod` files on deployment servers:

```bash
# .env.staging
APP_ENV=staging
REGISTRY=ghcr.io
IMAGE_NAME=YOUR_ORG/anpr/api
POSTGRES_PASSWORD=<generate_random_32_char_password>
REDIS_PASSWORD=<generate_random_32_char_password>
FERNET_KEY=<generate_via_python: from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())>
JWT_SECRET=<32+ character random string>
SECRET_KEY=<32+ character random string>
```

```bash
# .env.prod
APP_ENV=production
REGISTRY=ghcr.io
IMAGE_NAME=YOUR_ORG/anpr/api
POSTGRES_PASSWORD=<generate_random_32_char_password>
REDIS_PASSWORD=<generate_random_32_char_password>
FERNET_KEY=<generate_via_python: from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())>
JWT_SECRET=<32+ character random string>
SECRET_KEY=<32+ character random string>
```

Load in deployment scripts:
```bash
source .env.staging  # or .env.prod
docker-compose -f docker-compose.staging.yml up -d
```

## CI Pipeline (`.github/workflows/ci.yml`)

Runs on every **push to main/develop** and **pull requests**.

### Jobs

#### 1. `lint`
- Ruff: Code style, imports, security checks
- Ruff format: Consistent formatting
- Mypy: Type checking

**Fail if:** Any linting or type errors found.

#### 2. `test`
- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/` (with real DB/Redis)
- Coverage: 75% minimum required

**Fail if:** Tests fail or coverage < 75%.

**Services:** PostgreSQL 16, Redis 7

#### 3. `security`
- pip-audit: Dependency vulnerability scanning
- Trivy: Filesystem scanning for misconfigurations

**Fail if:** Critical vulnerabilities found.

#### 4. `build-image`
- **Runs only if:** lint, test, security pass
- Builds Docker image from `Dockerfile.api`
- Pushes to GHCR with tags:
  - `branch-COMMIT_SHA` (e.g., `main-abc1234`)
  - `latest` (if main branch)
  - Semantic version tags (if tagged release)
- Scans image with Trivy

#### 5. `smoke-test` (PR only)
- Starts API container
- Verifies `/healthz` responds with 200
- Tests POST `/health` endpoint

#### 6. `status-check`
- Gates branch protection: all checks must pass

## Staging Deployment (`.github/workflows/deploy-staging.yml`)

**Triggered by:** Merge to main branch (automatic)

**Manual override:** Workflow dispatch via GitHub UI

### Steps

1. Determine image tag from commit SHA
2. Create GitHub deployment record
3. SSH into staging server and deploy via docker-compose
4. Health check API
5. Run smoke tests
6. Mark deployment successful/failed
7. Notify Slack

### Deployment Method

Uses docker-compose and SSH. On staging server:

```bash
# /opt/anpr/staging/
git pull origin main
export IMAGE_TAG=main-abc1234
docker-compose -f docker-compose.staging.yml pull api worker
docker-compose -f docker-compose.staging.yml up -d api worker
```

**Rollback:** Manual via GitHub Actions workflow

## Production Deployment (`.github/workflows/deploy-prod.yml`)

**Triggered by:** Git tag matching `v[0-9]+.[0-9]+.[0-9]+` (semantic versioning)

**Example:** Tag `v1.2.3` triggers production deployment.

**Manual approval:** Required via GitHub environment protection rules.

### Steps

1. Validate semantic version tag
2. Verify tag exists on main branch (prevent deployments from branches)
3. Create GitHub deployment record
4. Pre-deployment health checks
5. **Blue-Green Deployment:**
   - Deploy to green (new) environment on port 8001
   - Wait for green to be healthy
   - Switch load balancer traffic: blue (8000) → green (8001)
   - Monitor for 2 minutes; check error rate
   - If healthy, keep green; shut down blue
   - If error, auto-rollback to blue
6. Post-deployment verification
7. Notify Slack
8. Create release notes (optional)

### Blue-Green Strategy

Two identical environments run simultaneously:

- **Blue (old):** Current production code
- **Green (new):** New code being deployed

**Advantages:**
- Zero-downtime deployments
- Instant rollback: just switch traffic back to blue
- Parallel testing before traffic switch

**Load Balancer Config:**
- Nginx upstream or HAProxy backend points to active environment
- Switch via `switch-traffic-to-green.sh` script

## Rollback (`.github/workflows/rollback-prod.yml`)

**Triggered manually:** via `gh workflow run rollback-prod.yml`

**Input:** Target version (tag) or "previous"

### Steps

1. Resolve target version (if "previous", get second-most-recent tag)
2. Stop current deployment
3. Pull and deploy target version
4. Health check
5. Mark deployment status
6. Notify Slack

**Example:**
```bash
gh workflow run rollback-prod.yml \
  --ref main \
  --raw-field target_version=v1.1.5 \
  --raw-field reason="High error rate detected in production"
```

## Semantic Versioning

Use [semver.org](https://semver.org/):

- **MAJOR** (X.0.0): Breaking API changes
- **MINOR** (0.X.0): New features, backward compatible
- **PATCH** (0.0.X): Bug fixes

Examples:
- `v0.1.0` → First release
- `v0.2.0` → New feature added
- `v0.2.1` → Bug fix
- `v1.0.0` → Production-ready release

To create a release:
```bash
git tag -a v0.1.0 -m "First release: basic ANPR inference + API"
git push origin v0.1.0
```

## Docker Image Tagging

Images are tagged with multiple identifiers for traceability:

```
ghcr.io/yourorg/anpr/api:main-abc1234    # Branch + commit
ghcr.io/yourorg/anpr/api:v0.1.0          # Semantic version
ghcr.io/yourorg/anpr/api:latest          # Latest on main
```

This allows:
- Tracing any deployment to exact source commit
- Pinning production to specific versions
- Instant rollback via semantic version tag

## Branch Protection Rules

Configure in **Settings → Branches → Branch protection rules** for `main`:

- ✅ Require a pull request before merging
- ✅ Require approvals (1 approval minimum)
- ✅ Dismiss stale pull request approvals
- ✅ Require status checks to pass before merging:
  - `lint`
  - `test`
  - `security`
  - `build-image`
  - `status-check`
- ✅ Require branches to be up to date before merging
- ✅ Require code reviews from code owners
- ✅ Require deployment to pass before merging (if using environments)
- ❌ Do NOT allow force pushes

## Deployment Environments

Configure in **Settings → Environments**:

### Staging
- No approval required
- Auto-deploys on main merge

### Production
- Require manual approval (at least 1 reviewer)
- Protection rules: only main branch can deploy
- Environment secrets: production credentials

This prevents accidental production deployments.

## GitHub Actions Configuration

### Concurrency

- **CI:** Multiple runs allowed (PR, push to different branches)
- **Staging deployment:** Single concurrent deployment (cancel previous)
- **Production deployment:** Single concurrent deployment (never cancel ongoing)

### Runners

All workflows use `ubuntu-latest` (GitHub-hosted runner).

To use self-hosted runner (e.g., on your infrastructure):
```yaml
runs-on: [self-hosted, linux, deployment]
```

### Permissions

Workflows request minimal permissions:
- `contents: read` — Read code
- `packages: write` — Push Docker images
- `packages: read` — Pull Docker images (deployments)
- `deployments: write` — Create GitHub deployments

## Troubleshooting

### CI checks failing

1. Check workflow run logs: **Actions → Workflow → Run → Job**
2. Lint errors: `uv run ruff check .`
3. Test failures: `uv run pytest tests/ -v`
4. Type errors: `uv run mypy anpr_core api workers db`

### Deployment fails

1. Check SSH connectivity: `ssh -i ~/.ssh/deploy_key deploy@staging-host`
2. Verify environment variables: `echo $DATABASE_URL` on server
3. Check Docker daemon: `docker ps` on server
4. View container logs: `docker-compose logs api`

### Rollback issues

1. Manual fix: SSH into production server
2. Check current version: `docker-compose ps`
3. Switch load balancer manually (if automated script fails)
4. Re-trigger workflow after fix

## Cost Optimization

- **GitHub Actions:** Free tier includes 2,000 minutes/month for private repos
- **Docker Registry (GHCR):** Free tier includes 500MB storage
- **Deployment servers:** Use auto-scaling or smaller instances in low-traffic windows

## Security Considerations

1. **Secrets:** Never commit secrets. Use GitHub Secrets Manager.
2. **SSH Keys:** Rotate deployment keys every 90 days.
3. **Code Review:** Require peer review before main merge.
4. **Approval Gates:** Require manual approval for production.
5. **Audit Logs:** GitHub provides audit logs for all deployments.
6. **Container Scanning:** Trivy scans every image for vulnerabilities.

## Next Steps

1. Create GitHub Secrets (see above)
2. Set up staging and production servers
3. Configure SSH key-based authentication
4. Test CI pipeline with a PR
5. Test staging deployment with a main merge
6. Create first git tag and test production deployment
7. Configure Slack notifications
8. Set up monitoring and alerting on production
