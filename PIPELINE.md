# ANPR CI/CD Pipeline

Production-grade CI/CD system for the FastAPI ANPR backend with automated testing, security scanning, staging deployments, and production blue-green rollouts.

## Quick Start

### For Developers

1. Push to PR → CI runs automatically (lint, test, security, build image)
2. Get review approval
3. Merge to main → Staging deployment automatic (~5 min)
4. Verify on staging: `curl https://staging-api.anpr.internal/healthz`

### For Release Manager

1. Create git tag: `git tag -a v0.1.0 -m "Release notes" && git push origin v0.1.0`
2. Wait for approval notification (requires manual approval in GitHub)
3. Approve deployment
4. Blue-green deployment to production (~10 min)
5. Verify: `curl https://api.anpr.com/healthz`

### For On-Call (Rollback)

If production is broken:

```bash
gh workflow run rollback-prod.yml \
  --ref main \
  --raw-field target_version=v0.0.X \
  --raw-field reason="Description of issue"
```

See `ops/RUNBOOK_ROLLBACK.md` for detailed instructions.

---

## Architecture

```
┌─────────────────┐
│ Developer Push  │
└────────┬────────┘
         │
    ┌────▼─────────────────────────────────┐
    │ GitHub Actions CI Pipeline            │
    ├────────────────────────────────────┬─┤
    │ • Lint (ruff, format, mypy)        │ │
    │ • Test (pytest, 75% coverage min)  │ │
    │ • Security (pip-audit, trivy)      │ │
    │ • Build Docker image               │ │
    │ • Smoke tests (health check)       │ │
    └────────────────────────────────────┴─┘
         │ (all pass)
    ┌────▼─────────────────────────────────┐
    │ Deploy to Staging (main merge only)  │
    │ • Docker compose up                  │
    │ • Health checks                      │
    │ • Smoke tests                        │
    └────────────────────────────────────┬─┘
         │ (staging healthy)
         │
    ┌────▼─────────────────────────────────┐
    │ Tag v*.*.* → Production Deployment   │
    │ • Manual approval (GitHub env)       │
    │ • Blue-green switch                  │
    │ • Monitoring & health checks         │
    │ • Auto-rollback if errors            │
    └────────────────────────────────────┬─┘
         │ (prod healthy)
    ┌────▼─────────────────────────────────┐
    │ Production Live                       │
    │ • Prometheus metrics                 │
    │ • Slack notifications                │
    │ • Audit logging                      │
    └────────────────────────────────────┘
```

---

## Files Overview

### Workflow Files (`.github/workflows/`)

| File | Trigger | Purpose |
|------|---------|---------|
| `ci.yml` | Push/PR to main/develop | Lint, test, build image, smoke test |
| `deploy-staging.yml` | Merge to main | Auto-deploy to staging + verify |
| `deploy-prod.yml` | Git tag v*.*.* | Manual approval + blue-green deploy to prod |
| `rollback-prod.yml` | Manual dispatch | Rollback to previous version |

### Configuration Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Local dev environment |
| `docker-compose.staging.yml` | Staging server environment |
| `docker-compose.prod.yml` | Production server environment |
| `Dockerfile.api` | Container image for API & workers |

### Documentation

| File | Audience | Purpose |
|------|----------|---------|
| `ops/CICD_SETUP.md` | DevOps, Team Lead | Complete pipeline setup & configuration |
| `ops/DEPLOYMENT_SERVER_SETUP.md` | DevOps, Infrastructure | Server provisioning walkthrough |
| `ops/DEPLOYMENT_CHECKLIST.md` | DevOps, Release Manager | Step-by-step deployment checklist |
| `ops/RUNBOOK_ROLLBACK.md` | On-Call Engineer | How to rollback production |

### Helper Scripts

| File | Purpose |
|------|---------|
| `scripts/switch-traffic-to-green.sh` | Switch LB to new (green) version |
| `scripts/switch-traffic-to-blue.sh` | Revert LB to old (blue) version |

---

## Key Features

### Automated Testing
- **Unit tests:** `tests/unit/` with pytest
- **Integration tests:** `tests/integration/` against real PostgreSQL + Redis
- **Coverage requirement:** 75% minimum
- **Test parallelization:** Runs on `ubuntu-latest` GitHub runner

### Security Scanning
- **Dependency scan:** `pip-audit` (checks for known vulnerabilities)
- **Filesystem scan:** Trivy (checks container config, secret patterns)
- **Code scan:** Built into ruff (security rules via S category)
- **Container image scan:** Trivy scans built Docker image

### Code Quality
- **Linting:** Ruff (pycodestyle, pyflakes, isort, security, and more)
- **Type checking:** Mypy (strict mode)
- **Formatting:** Ruff format (auto-formatters like Black)
- **Coverage:** Pytest-cov with 75% threshold

### Deployment Strategies

**Staging:** Simple auto-deployment on main merge
- Docker-compose pull + up
- Health checks verify API responds
- Smoke tests run against staging URL

**Production:** Blue-green with manual approval
- GitHub environment protection (requires approval)
- Deploy to new (green) environment on separate port
- Switch load balancer after health checks
- Monitor for 2 minutes (check error rate)
- Auto-rollback if degradation detected
- Keep old (blue) environment available for instant rollback

### Rollback
- **Manual trigger:** GitHub Actions workflow dispatch
- **Support for:** Rollback to specific tag or "previous" version
- **Speed:** < 5 minutes
- **Reversible:** Keep stable version running during rollback

---

## GitHub Secrets Required

Set these in **Settings → Secrets and variables → Actions**:

```
STAGING_DEPLOY_HOST    = staging-server.example.com
STAGING_DEPLOY_USER    = deploy
STAGING_DEPLOY_KEY     = (SSH private key)

PROD_DEPLOY_HOST       = prod-server.example.com
PROD_DEPLOY_USER       = deploy
PROD_DEPLOY_KEY        = (SSH private key)

SLACK_WEBHOOK_DEPLOY   = https://hooks.slack.com/services/...
```

No need to set `REGISTRY` (defaults to ghcr.io) or `IMAGE_NAME` (derived from repo).

---

## Environment Variables

### Staging (`.env.staging` on server)
```
APP_ENV=staging
POSTGRES_PASSWORD=<random_32_chars>
REDIS_PASSWORD=<random_32_chars>
FERNET_KEY=<from cryptography.fernet>
JWT_SECRET=<random_32_chars>
SECRET_KEY=<random_32_chars>
```

### Production (`.env.prod` on server)
```
APP_ENV=production
POSTGRES_PASSWORD=<random_32_chars>
REDIS_PASSWORD=<random_32_chars>
FERNET_KEY=<from cryptography.fernet>
JWT_SECRET=<random_32_chars>
SECRET_KEY=<random_32_chars>
```

**Security:** Store `.env.*` files securely on servers. Never commit to git. Rotate secrets every 90 days.

---

## Typical Workflow

### Deploy a Feature

```bash
# Feature branch + PR
git checkout -b feat/new-endpoint
# ... code changes ...
git push origin feat/new-endpoint
# Open PR, describe changes

# GitHub Actions automatically runs:
# 1. Lint (ruff check, ruff format)
# 2. Type check (mypy)
# 3. Unit tests (pytest)
# 4. Integration tests (against real DB)
# 5. Security scan (pip-audit, trivy)
# 6. Build Docker image
# 7. Smoke test (health check)

# If all pass: you can merge
# Get code review approval
git merge --squash origin/main
git commit -m "feat: new endpoint"
git push origin main

# GitHub Actions automatically deploys to staging
# Check staging: curl https://staging-api.anpr.internal/health
# Run manual tests, verify feature works
```

### Release to Production

```bash
# Verify everything is on main and working in staging
git checkout main
git pull origin main

# Create semantic version tag
git tag -a v0.1.0 -m "Release: new endpoint + bug fixes"
git push origin v0.1.0

# GitHub Actions triggers deploy-prod.yml
# Workflow will request manual approval

# Check email / GitHub for approval notification
# Visit GitHub Actions, click "Review deployments"
# Click "Approve and deploy"

# Blue-green deployment executes:
# 1. Deploy to green on port 8001
# 2. Health check green
# 3. Switch load balancer to green
# 4. Monitor error rate for 2 min
# 5. If healthy: keep green, shut down blue
# 6. If degradation: auto-rollback to blue

# Verify production: curl https://api.anpr.com/healthz
# Slack notification sent with deployment status
```

### Emergency Rollback

```bash
# Production is broken
# Trigger rollback workflow:

gh workflow run rollback-prod.yml \
  --ref main \
  --raw-field target_version=v0.0.5 \
  --raw-field reason="Database migration caused 10% error rate"

# Or use GitHub UI:
# Actions → Rollback Production → Run workflow
# Input: v0.0.5, reason
# Click "Run workflow"

# Workflow executes:
# 1. Stop current deployment
# 2. Pull previous version image
# 3. Start containers
# 4. Health check
# 5. Switch load balancer back
# 6. Slack notification

# Verify: curl https://api.anpr.com/healthz
# Should be responding again
```

---

## Monitoring & Alerting

After production deployment, set up (optional but recommended):

- **Prometheus:** Scrapes metrics from API, database, workers
- **Grafana:** Dashboards for latency, error rate, resource usage
- **Alerts:**
  - Error rate > 2% → Page on-call engineer
  - Latency p99 > 500ms → Page on-call engineer
  - Database connections > 90 → Alert ops
  - Disk usage > 80% → Alert ops

See `ops/DEPLOYMENT_SERVER_SETUP.md` section 7 for setup.

---

## Cost & Performance

**GitHub Actions:** 
- Free tier: 2,000 minutes/month for private repos
- Cost: $0 for public repos, $0.008/min for private (if over quota)
- Typical CI run: 5–8 minutes

**Container Registry (GHCR):**
- Free tier: 500 MB storage
- Cost: $0 for public, $0.25/GB/month for storage if over quota

**Deployment Servers:**
- Staging: t3.medium (1 vCPU, 4 GB RAM) = ~$30/month
- Production: t3.large (2 vCPU, 8 GB RAM) = ~$60/month

---

## Troubleshooting

### CI Pipeline Fails

1. Check workflow logs: **Actions → Workflow run → Job**
2. Common issues:
   - **Lint errors:** Run `uv run ruff check .` locally
   - **Test failures:** Run `uv run pytest tests/ -v` locally
   - **Type errors:** Run `uv run mypy anpr_core api workers db`

### Staging Deployment Fails

1. Check deployment logs in GitHub Actions
2. SSH into staging server: `ssh deploy@staging-server`
3. Check containers: `docker-compose -f /opt/anpr/docker-compose.staging.yml ps`
4. Check logs: `docker-compose logs api`
5. Verify secrets: `echo $DATABASE_URL` (should not be empty)

### Production Deployment Fails

1. Check approval notification (email or GitHub)
2. Verify SSH key on prod server: `ssh -i ~/.ssh/anpr-prod-deploy deploy@prod-server`
3. Check load balancer: `sudo systemctl status nginx`
4. Manual fix: See `ops/RUNBOOK_ROLLBACK.md` → Step 4 (Manual Rollback)

### Rollback Fails

1. SSH into production manually
2. Stop current: `docker-compose -f docker-compose.prod.yml down`
3. Pull previous: `docker-compose pull && docker-compose up -d`
4. Health check: `curl http://localhost:8000/healthz`
5. If still broken, revert load balancer config manually

---

## Best Practices

1. **Always test in staging first** before production release
2. **Use semantic versioning** for releases (v1.2.3, not v1 or latest)
3. **Require code review** on all PRs before merge
4. **Require manual approval** for production deployments
5. **Monitor error rate** after each deployment (30 min post-deploy)
6. **Keep rollback runbook** accessible to on-call team
7. **Rotate secrets** every 90 days
8. **Test rollback** monthly with on-call engineer

---

## Related Documentation

- **Setup:** See `ops/CICD_SETUP.md`
- **Server Setup:** See `ops/DEPLOYMENT_SERVER_SETUP.md`
- **Rollback:** See `ops/RUNBOOK_ROLLBACK.md`
- **Checklist:** See `ops/DEPLOYMENT_CHECKLIST.md`

---

## Questions?

For CI/CD issues, check:
1. `ops/CICD_SETUP.md` → Troubleshooting section
2. `ops/DEPLOYMENT_SERVER_SETUP.md` → Troubleshooting section
3. GitHub Actions workflow logs (Actions → Workflow → Run)
4. Server logs: `docker-compose logs -f`

For deployment issues, refer to `ops/RUNBOOK_ROLLBACK.md`.

---

**Last Updated:** 2026-05-28
**Maintained By:** DevOps Team
**Review Frequency:** Quarterly
