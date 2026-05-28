# Deployment Checklist

Use this checklist to set up the complete CI/CD pipeline for ANPR.

---

## Phase 1: Local Development (Day 1)

- [ ] Verify tests pass locally: `uv run pytest tests/ -v --cov`
- [ ] Verify linting passes: `uv run ruff check .`
- [ ] Verify type checking passes: `uv run mypy anpr_core api workers db`
- [ ] Build Docker image locally: `docker build -f Dockerfile.api -t anpr-api:test .`
- [ ] Run docker-compose locally: `docker-compose up -d && curl http://localhost:8000/healthz`

---

## Phase 2: GitHub Actions Setup (Day 1–2)

### 2A: Repository Secrets

Set up in **Settings → Secrets and variables → Actions**:

- [ ] `SLACK_WEBHOOK_DEPLOY` = Slack webhook URL for notifications
  - Create at: https://api.slack.com/apps → Your App → Incoming Webhooks
- [ ] Commit `.github/workflows/ci.yml` to repo
- [ ] Commit `.github/workflows/deploy-staging.yml` to repo
- [ ] Commit `.github/workflows/deploy-prod.yml` to repo
- [ ] Commit `.github/workflows/rollback-prod.yml` to repo

### 2B: Test CI Pipeline

- [ ] Create test PR: `git checkout -b test/ci && echo "# test" >> README.md && git push`
- [ ] Watch CI run: **Actions → PR workflow**
- [ ] Verify all jobs pass: lint, test, security, build-image, smoke-test
- [ ] Merge PR to main

---

## Phase 3: Staging Server Setup (Day 2–3)

### 3A: Provision Server

- [ ] Create Ubuntu 20.04+ VM on your infrastructure
- [ ] Assign public IP address
- [ ] Create DNS A record: `staging-api.anpr.internal` → IP
- [ ] SSH access from local machine

### 3B: SSH Key Configuration

On **local machine**:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/anpr-staging-deploy -N ""
```

- [ ] Public key uploaded to server: `~/.ssh/authorized_keys`
- [ ] Test passwordless login: `ssh -i ~/.ssh/anpr-staging-deploy deploy@staging-server echo OK`
- [ ] Add secret to GitHub: `STAGING_DEPLOY_HOST`, `STAGING_DEPLOY_USER`, `STAGING_DEPLOY_KEY`

### 3C: Server Dependencies

SSH into server and run:
```bash
bash ops/DEPLOYMENT_SERVER_SETUP.md  # Follow installation steps
```

- [ ] Docker installed and daemon running
- [ ] Docker Compose installed
- [ ] PostgreSQL client installed
- [ ] Nginx installed and running
- [ ] SSL certificate obtained (Let's Encrypt)
- [ ] GitHub Container Registry credentials configured

### 3D: Deploy Directory

- [ ] `/opt/anpr` directory created and owned by `deploy` user
- [ ] `.env.staging` file created with secrets
- [ ] `docker-compose.staging.yml` in repo
- [ ] `deploy-staging.sh` script created and executable

### 3E: Test Staging Deployment

Merge test PR to main:
```bash
git checkout -b test/deploy
echo "# Deploy test" >> README.md
git push origin test/deploy
# Open PR, merge to main
```

- [ ] GitHub Actions triggers `deploy-staging.yml` automatically
- [ ] Workflow completes successfully
- [ ] Verify: `curl https://staging-api.anpr.internal/healthz` returns 200
- [ ] Check logs: `ssh deploy@staging-server docker-compose -f /opt/anpr/docker-compose.staging.yml logs api`

---

## Phase 4: Production Server Setup (Day 3–4)

### 4A: Provision Server

- [ ] Create Ubuntu 20.04+ VM on production infrastructure
- [ ] Assign public IP address
- [ ] Create DNS A record: `api.anpr.com` (or your domain) → IP
- [ ] SSH access from local machine

### 4B: SSH Key Configuration

On **local machine**:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/anpr-prod-deploy -N ""
```

- [ ] Public key uploaded to server
- [ ] Test passwordless login
- [ ] Add secret to GitHub: `PROD_DEPLOY_HOST`, `PROD_DEPLOY_USER`, `PROD_DEPLOY_KEY`

### 4C: Server Dependencies

SSH into server and repeat Phase 3C steps.

### 4D: Deploy Directory

- [ ] `/opt/anpr` directory created
- [ ] `.env.prod` file created with **strong** secrets:
  - [ ] `POSTGRES_PASSWORD`: 32-char random
  - [ ] `REDIS_PASSWORD`: 32-char random
  - [ ] `JWT_SECRET`: 32-char random
  - [ ] `FERNET_KEY`: Generated via Cryptography library
  - [ ] `SECRET_KEY`: 32-char random
- [ ] Store secrets securely (password manager, HashiCorp Vault, etc.)
- [ ] `docker-compose.prod.yml` in repo
- [ ] `docker-compose.prod.green.yml` (copy of prod for blue-green) in repo

### 4E: Load Balancer Configuration

For blue-green deployments:

- [ ] Primary load balancer configured to route to blue (port 8000)
- [ ] `switch-traffic-to-green.sh` script in place
- [ ] `switch-traffic-to-blue.sh` script in place
- [ ] Tested traffic switching manually

---

## Phase 5: Monitoring & Alerting (Day 4–5)

### 5A: Prometheus (Optional but Recommended)

- [ ] Prometheus container added to `docker-compose.prod.yml`
- [ ] Node Exporter installed on server
- [ ] Prometheus scrapes metrics from containers
- [ ] Verify: `curl http://staging-server:9090/graph`

### 5B: Grafana (Optional)

- [ ] Grafana container deployed
- [ ] Connected to Prometheus data source
- [ ] Created dashboards: API health, database, workers
- [ ] Created alert rules:
  - [ ] Error rate > 2% → Page on-call
  - [ ] Latency p99 > 500ms → Page on-call
  - [ ] Database connections > 90 → Alert

### 5C: Slack Notifications

- [ ] Deployment notifications working (test with staging deployment)
- [ ] Alert notifications working (trigger test alert)

---

## Phase 6: Release & Deploy to Production (Day 5–6)

### 6A: Create First Release

```bash
# Make sure all changes are on main
git checkout main
git pull origin main

# Create semantic version tag
git tag -a v0.1.0 -m "First production release"
git push origin v0.1.0
```

- [ ] Git tag created with semantic version (v0.1.0)
- [ ] Tag pushed to GitHub

### 6B: GitHub Environment Protection (Production)

Set up in **Settings → Environments → production**:

- [ ] Require manual approval (assign to 1+ team member)
- [ ] Protection rules: only `main` branch can deploy
- [ ] Environment secrets: none needed (uses repo secrets)

### 6C: Monitor Deployment

- [ ] GitHub Actions workflow `deploy-prod.yml` triggers
- [ ] Approval requested (check email/PagerDuty)
- [ ] Approval granted
- [ ] Blue-green deployment executes
- [ ] Monitor logs in real-time
- [ ] Post-deployment health checks pass

### 6D: Production Verification

- [ ] Health check: `curl https://api.anpr.com/healthz`
- [ ] Status endpoint: `curl https://api.anpr.com/api/v1/status`
- [ ] Metrics visible in Grafana
- [ ] Slack notification received
- [ ] Team notified via email/Slack

---

## Phase 7: Rollback Testing (Day 6)

### 7A: Prepare for Rollback

- [ ] Read `ops/RUNBOOK_ROLLBACK.md` thoroughly
- [ ] Understand blue-green switching mechanism
- [ ] Know how to rollback via GitHub Actions and manual process

### 7B: Test Rollback (Staging)

On staging server:

```bash
# Create "failure" in current version (e.g., break health check endpoint)
# Then trigger rollback workflow
```

- [ ] Rollback workflow triggered successfully
- [ ] Service recovered to previous version
- [ ] Health checks pass after rollback

### 7C: Production Rollback Preparation

- [ ] Document current production version (`v0.1.0`)
- [ ] Note location of rollback runbook for on-call team
- [ ] Share runbook with team

---

## Phase 8: Documentation & Training (Day 6–7)

- [ ] Share `CICD_SETUP.md` with team
- [ ] Share `RUNBOOK_ROLLBACK.md` with on-call engineer
- [ ] Share `DEPLOYMENT_SERVER_SETUP.md` with infrastructure team
- [ ] Walk through GitHub Actions workflow with team
- [ ] Practice rollback scenario with on-call engineer
- [ ] Create team Slack channel for deployment notifications

---

## Phase 9: Ongoing Maintenance

### Weekly
- [ ] Review deployment logs for errors
- [ ] Check security scan results in GitHub
- [ ] Verify backups are working

### Monthly
- [ ] Rotate secrets (SSH keys, API keys)
- [ ] Update base Docker images
- [ ] Test disaster recovery (restore from backup)
- [ ] Review and optimize Docker image size

### Quarterly
- [ ] Review and update CI/CD documentation
- [ ] Assess pipeline performance (build times)
- [ ] Hold blameless post-mortem if incidents occurred
- [ ] Plan upgrades (Docker, Postgres, etc.)

---

## Quick Links

| Document | Purpose |
|----------|---------|
| `CICD_SETUP.md` | Detailed pipeline documentation |
| `DEPLOYMENT_SERVER_SETUP.md` | Server provisioning guide |
| `RUNBOOK_ROLLBACK.md` | How to rollback production |
| `.github/workflows/ci.yml` | CI pipeline definition |
| `.github/workflows/deploy-staging.yml` | Staging deployment |
| `.github/workflows/deploy-prod.yml` | Production deployment |
| `.github/workflows/rollback-prod.yml` | Rollback workflow |
| `docker-compose.staging.yml` | Staging containers |
| `docker-compose.prod.yml` | Production containers |

---

## Common Issues & Fixes

### "Permission denied (publickey)" during deployment

**Fix:** SSH key not configured correctly
```bash
ssh -i ~/.ssh/anpr-staging-deploy -vvv deploy@staging-server
# Check ~/.ssh/authorized_keys on server
```

### "Repository not found" error in GitHub Actions

**Fix:** GITHUB_TOKEN not being used correctly
```yaml
- uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}  # Built-in, no additional secret needed
```

### "Connection refused" on localhost:8000 after deployment

**Fix:** Container not started or health check failed
```bash
docker-compose -f docker-compose.staging.yml logs api
docker-compose -f docker-compose.staging.yml ps
```

### "Database migrations failed"

**Fix:** Schema mismatch between app and DB
```bash
# Check migration status
docker-compose exec api alembic current
# See pending migrations
docker-compose exec api alembic heads
```

---

## Success Criteria

You've successfully set up the CI/CD pipeline when:

1. ✅ PR merge to main → Staging deployment (< 5 min)
2. ✅ Git tag v*.*.* → Production deployment (< 10 min)
3. ✅ Health checks pass at every stage
4. ✅ Rollback completes in < 5 minutes
5. ✅ Team receives Slack notifications
6. ✅ Zero manual steps required for deployment
7. ✅ On-call can rollback without dev intervention
8. ✅ All secrets stored securely (no hardcoding)
9. ✅ Tests run on every commit
10. ✅ Linting and type-checking automated

---

## After Deployment

Once in production, set up:

1. **Monitoring:** Prometheus + Grafana dashboards
2. **Alerting:** Error rate, latency, database health
3. **Logging:** Centralized logs (CloudWatch, ELK, Datadog)
4. **Backup:** Automated daily backups with recovery testing
5. **On-call:** Rotation schedule with runbooks
6. **Incident Response:** Post-mortem process and playbooks
7. **Cost Tracking:** Monitor resource usage and optimize

See `MONITORING.md` (to be created) for setup details.

---

## Questions?

Reach out to the DevOps team or check the related documentation files.
