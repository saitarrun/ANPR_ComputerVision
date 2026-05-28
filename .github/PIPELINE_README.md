# CI/CD Pipeline for ANPR Backend

This directory contains GitHub Actions workflows for the FastAPI ANPR backend CI/CD pipeline.

## Quick Links

- **Architecture & Overview:** [../../PIPELINE.md](../../PIPELINE.md)
- **Detailed Setup Guide:** [../../ops/CICD_SETUP.md](../../ops/CICD_SETUP.md)
- **Server Provisioning:** [../../ops/DEPLOYMENT_SERVER_SETUP.md](../../ops/DEPLOYMENT_SERVER_SETUP.md)
- **Rollback Runbook:** [../../ops/RUNBOOK_ROLLBACK.md](../../ops/RUNBOOK_ROLLBACK.md)
- **Implementation Checklist:** [../../ops/DEPLOYMENT_CHECKLIST.md](../../ops/DEPLOYMENT_CHECKLIST.md)

## Workflows

### ci.yml
Lint, test, security scan, and build image on every commit.

**Triggers:** `push` to main/develop, `pull_request` to main/develop

**Steps:**
1. Lint (ruff)
2. Test (pytest with 75% coverage)
3. Security (pip-audit, trivy)
4. Build Docker image
5. Smoke tests (health check)

**Fail Criteria:** Any test failure, coverage < 75%, security scan findings

### deploy-staging.yml
Automatic deployment to staging on main branch merge.

**Triggers:** `push` to main, manual workflow dispatch

**Steps:**
1. Pull latest code
2. Deploy via docker-compose to staging server
3. Health checks
4. Smoke tests
5. Slack notification

**Environment:** Staging (requires `STAGING_DEPLOY_HOST`, `STAGING_DEPLOY_USER`, `STAGING_DEPLOY_KEY`)

### deploy-prod.yml
Blue-green deployment to production on semantic version tag.

**Triggers:** Git tag matching `v[0-9]+.[0-9]+.[0-9]+`, manual workflow dispatch

**Steps:**
1. Validate semantic version
2. Manual approval gate (GitHub environment)
3. Deploy to green environment (port 8001)
4. Health checks
5. Switch load balancer traffic
6. Monitor for errors (2 min)
7. Auto-rollback if degradation detected
8. Slack notification

**Environment:** Production (requires `PROD_DEPLOY_HOST`, `PROD_DEPLOY_USER`, `PROD_DEPLOY_KEY`)

**Approval:** Configured via GitHub Settings > Environments > production

### rollback-prod.yml
Emergency rollback to previous production version.

**Triggers:** Manual workflow dispatch

**Inputs:**
- `target_version`: Version to rollback to (v0.1.0 format or "previous")
- `reason`: Reason for rollback (for audit/Slack)

**Steps:**
1. Resolve target version
2. Stop current deployment
3. Pull and deploy target version
4. Health checks
5. Slack notification

**Time to Recovery:** 5-10 minutes

## Required GitHub Secrets

Set in **Settings → Secrets and variables → Actions**:

```
STAGING_DEPLOY_HOST    = staging.example.com
STAGING_DEPLOY_USER    = deploy
STAGING_DEPLOY_KEY     = (SSH private key)

PROD_DEPLOY_HOST       = prod.example.com
PROD_DEPLOY_USER       = deploy
PROD_DEPLOY_KEY        = (SSH private key)

SLACK_WEBHOOK_DEPLOY   = https://hooks.slack.com/services/...
```

## Branch Protection Rules

Configure for `main` branch:

- Require pull request before merging
- Require 1 approval
- Require status checks: `lint`, `test`, `security`, `build-image`, `status-check`
- Require branches to be up-to-date
- No force-push to main

## Typical Usage

### Deploy a Feature
```bash
git checkout -b feat/new-endpoint
# ... code ...
git push origin feat/new-endpoint
# → GitHub Actions runs CI
# Get PR review approval
# Merge to main
# → GitHub Actions auto-deploys to staging
```

### Release to Production
```bash
git tag -a v0.1.0 -m "Release notes"
git push origin v0.1.0
# → GitHub Actions triggers deploy-prod.yml
# → Email approval request sent
# → Approve in GitHub Actions
# → Blue-green deployment executes
```

### Rollback Production
```bash
gh workflow run rollback-prod.yml \
  --ref main \
  --raw-field target_version=v0.0.5 \
  --raw-field reason="Error rate spike"
# Or use GitHub UI: Actions → Rollback Production → Run workflow
```

## Troubleshooting

See [../../ops/CICD_SETUP.md](../../ops/CICD_SETUP.md#troubleshooting) for CI issues.

See [../../ops/DEPLOYMENT_SERVER_SETUP.md](../../ops/DEPLOYMENT_SERVER_SETUP.md#troubleshooting) for server issues.

See [../../ops/RUNBOOK_ROLLBACK.md](../../ops/RUNBOOK_ROLLBACK.md) for production incidents.

## Related Documentation

| Document | Purpose |
|----------|---------|
| [../../PIPELINE.md](../../PIPELINE.md) | High-level architecture & quick reference |
| [../../ops/CICD_SETUP.md](../../ops/CICD_SETUP.md) | Detailed setup guide |
| [../../ops/DEPLOYMENT_SERVER_SETUP.md](../../ops/DEPLOYMENT_SERVER_SETUP.md) | Server provisioning |
| [../../ops/DEPLOYMENT_CHECKLIST.md](../../ops/DEPLOYMENT_CHECKLIST.md) | Implementation steps |
| [../../ops/RUNBOOK_ROLLBACK.md](../../ops/RUNBOOK_ROLLBACK.md) | On-call playbook |
