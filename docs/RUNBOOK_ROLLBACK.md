# Production Rollback Runbook

## Quick Reference

**Situation:** Production is down or degraded. Need to rollback to previous version.

**Time Estimate:** 5–10 minutes

**On-call:** Follow this runbook to restore service.

---

## Prerequisites

- Access to GitHub Actions
- SSH access to production server
- Slack notification ability

---

## Step 1: Determine Rollback Target

### Option A: Rollback to Previous Version (Recommended)

If you're not sure which version had the issue:

```bash
# Get list of recent releases
git tag --sort=-version:refname --list 'v*' | head -5

# Example output:
# v0.2.3  (current, broken)
# v0.2.2  (previous, known-good)
# v0.2.1
# v0.2.0
```

Target: **v0.2.2** (previous stable version)

### Option B: Rollback to Specific Version

If you know which version to rollback to:

```bash
TARGET_VERSION="v0.2.1"
```

### Option C: Rollback to Last Known-Good

Check deployment history:

```bash
# View recent deployments
gh api repos/:owner/:repo/deployments?environment=production --paginate

# Check commit that was deployed
git log --oneline v0.2.2
```

---

## Step 2: Trigger Rollback via GitHub Actions

### Method 1: GitHub UI (Recommended)

1. Go to **Actions → Rollback Production**
2. Click **Run Workflow** (blue button, top-right)
3. Fill in:
   - **target_version:** `v0.2.2` (or `previous`)
   - **reason:** `High error rate detected. API latency spike at 2026-05-28 14:30 UTC.`
4. Click **Run Workflow**

Monitor the workflow:
- **In Progress:** Check logs in real-time
- **Success:** Service restored (Slack notification sent)
- **Failure:** See manual recovery steps below

### Method 2: CLI

```bash
gh workflow run rollback-prod.yml \
  --ref main \
  --raw-field target_version=v0.2.2 \
  --raw-field reason="High error rate: rate increased from 0.1% to 5%"
```

View status:
```bash
gh run list --workflow=rollback-prod.yml --limit=1
gh run view <RUN_ID> --log
```

---

## Step 3: Verify Rollback Success

### Check Deployment Status

```bash
# Check GitHub deployment status
gh deployment list --repo . | head -5

# View latest deployment details
gh api repos/:owner/:repo/deployments/latest
```

### Health Checks (Manual)

```bash
# API health
curl -f https://api.anpr.com/healthz
# Expected: 200 OK

# Status endpoint
curl https://api.anpr.com/api/v1/status | jq .
# Expected: {"status": "healthy", "version": "v0.2.2"}

# Database connectivity
curl -X POST https://api.anpr.com/api/v1/test-db
# Expected: 200 OK with connection info
```

### Check Logs

```bash
# SSH into production server
ssh deploy@prod-server

# View current containers
docker-compose -f /opt/anpr/prod/docker-compose.yml ps

# Check API container logs
docker logs anpr_api_prod --tail=50 -f

# Check worker logs
docker logs anpr_worker_prod --tail=50 -f
```

### Check Metrics

If monitoring is set up (Prometheus, Grafana):

1. Navigate to Grafana: https://grafana.anpr.com
2. Open dashboard: **ANPR Production**
3. Verify (should return to baseline within 2 min post-rollback):
   - Error rate (5xx): < 1%
   - API latency (p99): < 500ms
   - Database query time (p99): < 100ms
   - Worker queue depth: < 100 jobs

---

## Step 4: Manual Rollback (If Automated Fails)

### Situation: GitHub Actions workflow failed

**Time to manual rollback:** 10–15 min

### 4A: SSH into Production Server

```bash
ssh deploy@prod-server
cd /opt/anpr/prod

# Check current status
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs api --tail=20
```

### 4B: Stop Current Deployment

```bash
docker-compose -f docker-compose.prod.yml down
```

### 4C: Deploy Previous Version

```bash
# Set target version
export IMAGE_TAG="v0.2.2"
export REGISTRY="ghcr.io"
export IMAGE_NAME="yourorg/anpr/api"

# Pull the image (requires GHCR auth)
docker login ghcr.io  # Use PAT if needed
docker-compose -f docker-compose.prod.yml pull api worker

# Start the deployment
docker-compose -f docker-compose.prod.yml up -d api worker
```

### 4D: Health Check

```bash
# Wait for startup (20–30 sec)
sleep 30

# Check health
docker-compose -f docker-compose.prod.yml exec api curl http://localhost:8000/healthz

# Expected: {"status": "ok"}
```

### 4E: Verify from Outside

```bash
# From local machine
curl -f https://api.anpr.com/healthz
```

**If health check fails:**
1. Check logs: `docker-compose logs -f api`
2. Check database: `docker-compose exec -T postgres psql -U anpr -d anpr -c "SELECT 1;"`
3. Check Redis: `docker-compose exec -T redis redis-cli ping`

---

## Step 5: Post-Rollback

### 5A: Notify Team

Send Slack message to #incidents:

> Production rollback completed. Rolled back from v0.2.3 → v0.2.2.
> Reason: 5% error rate spike
> Status: Healthy. Error rate now 0.1%.
> Next: Root cause analysis of v0.2.3 issue.

### 5B: Investigation

On-call engineer should:

1. **Check commit diff:**
   ```bash
   git diff v0.2.2 v0.2.3
   ```

2. **Review logs from v0.2.3:**
   ```bash
   # View logs from the failed deployment
   docker logs <container_id> --until=2026-05-28T14:45:00.000000000Z | grep -i error
   ```

3. **Identify root cause:**
   - Was it a code change?
   - Was it a dependency issue?
   - Was it infrastructure (database, Redis)?

4. **Create incident report** (see INCIDENT_REPORT.md template)

### 5C: Fix and Re-deploy

Once root cause is identified and fixed:

```bash
# Update code
git checkout develop
git pull origin develop

# Create fix branch
git checkout -b fix/issue-description

# Make changes, test locally
uv run pytest tests/ -v

# Commit and push
git add .
git commit -m "Fix: description of issue"
git push origin fix/issue-description

# Open PR, get review, merge to main
# Then tag new release
git tag -a v0.2.4 -m "Fix: description"
git push origin v0.2.4

# GitHub Actions will auto-deploy to production
```

---

## Step 6: Communication Timeline

| Time | Action | Who |
|------|--------|-----|
| T+0m | Incident detected | Monitoring/On-call |
| T+2m | P1 alert sent | PagerDuty |
| T+5m | On-call acks alert | On-call engineer |
| T+7m | Rollback initiated (GitHub Actions) | On-call engineer |
| T+12m | Rollback complete, service healthy | GitHub Actions + Manual verification |
| T+15m | Slack #incidents notification | On-call engineer |
| T+30m | Initial investigation note | On-call engineer |
| T+24h | Full incident report | On-call engineer |

---

## Common Scenarios & Solutions

### Scenario 1: Database Migration Failed

**Symptom:** API crashes on startup, logs show "migration failed"

**Cause:** v0.2.3 had database schema change that broke compatibility

**Solution:**
1. Rollback to v0.2.2 (see steps above)
2. Do NOT re-apply schema. Revert to previous schema if needed:
   ```bash
   cd /opt/anpr/prod
   # Downgrade schema
   docker-compose exec api alembic downgrade -1
   ```

### Scenario 2: Redis Connection Pool Exhaustion

**Symptom:** API responds slowly, logs show "Redis connection timeout"

**Cause:** v0.2.3 introduced a Redis connection leak

**Solution:**
1. Rollback to v0.2.2
2. Manually flush Redis (optional):
   ```bash
   docker-compose exec redis redis-cli FLUSHALL
   ```

### Scenario 3: Load Balancer Not Updated

**Symptom:** Rollback completed, but old version still serving requests

**Cause:** Load balancer/nginx config not switched

**Solution:**
```bash
# Check load balancer config
sudo cat /etc/nginx/conf.d/anpr-upstream.conf

# If pointing to port 8000 but deployment is on 8001, manually update:
sudo sed -i 's/8001/8000/' /etc/nginx/conf.d/anpr-upstream.conf
sudo nginx -t && sudo systemctl reload nginx
```

### Scenario 4: Rolling Back to Really Old Version

**Symptom:** Need to rollback more than one version (e.g., v0.2.3 → v0.2.1)

**Solution:** Same steps. Just change `IMAGE_TAG`:
```bash
export IMAGE_TAG="v0.2.1"  # or v0.1.5, doesn't matter
docker-compose pull api worker
docker-compose up -d api worker
```

**Warning:** If rolling back more than 2 versions, verify database schema compatibility:
```bash
docker-compose exec api python -c "from db.models import *; print('Schema OK')"
```

---

## Escalation Path

**If rollback fails or you're unsure:**

1. **First:** Check logs and try manual fix above
2. **Second:** Page secondary on-call engineer for assistance
3. **Third (if both fail):** Page engineering lead + infrastructure team
4. **Last resort:** Rollback entire infrastructure to previous snapshot (if available)

---

## Prevention

To prevent future incidents:

1. **Test staging first:** Always deploy to staging and verify for 1+ hours before production
2. **Canary deployments:** Deploy to small % of traffic before full rollout
3. **Automated monitoring:** Set up alerts for error rate > 2%, latency > 500ms
4. **Blue-green:** Always use blue-green. Instant rollback is safer than multi-step process.

---

## Related Docs

- `CICD_SETUP.md` — Full pipeline documentation
- `INCIDENT_REPORT.md` — Template for post-incident analysis
- `MONITORING.md` — Metrics, dashboards, alerting setup
