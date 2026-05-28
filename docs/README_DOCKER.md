# Docker Compose: M6 Infrastructure Setup

## Overview

Complete Docker Compose stack for ANPR M6 (FastAPI backend + Celery workers + observability).

**7 services:**
1. **postgres** — PostgreSQL 16 (port 5432)
2. **redis** — Redis 7 (port 6379)
3. **minio** — MinIO S3-compatible (ports 9000/9001)
4. **prometheus** — Prometheus monitoring (port 9090)
5. **grafana** — Grafana dashboards (port 3001)
6. **api** — FastAPI application (port 8000) ✨ NEW
7. **worker** — Celery task queue (internal) ✨ NEW

## Prerequisites

- Docker and Docker Compose (v2+)
- OrbStack (macOS, optional; use Docker Desktop as fallback)
- Python 3.11+ and pyproject.toml dependencies installed locally

## Quick Start

### 1. Prepare Environment

Copy `.env.example` to `.env` and update secrets:

```bash
cd /Users/saitarrunpitta/Projects/ComputerVision\ Project
cp .env.example .env
```

Generate secure secrets (if needed):

```bash
python3 << 'EOF'
import secrets
import base64

secret_key = secrets.token_urlsafe(32)
jwt_secret = secrets.token_urlsafe(32)
fernet_key = base64.b64encode(secrets.token_bytes(32)).decode()

print(f"SECRET_KEY={secret_key}")
print(f"JWT_SECRET={jwt_secret}")
print(f"FERNET_KEY={fernet_key}")
EOF
```

Update `.env` with the generated values.

### 2. Build Services

Build all images (or individual services):

```bash
cd /Users/saitarrunpitta/Projects/ComputerVision\ Project
docker-compose -f ops/docker-compose.yml build

# Or build individual services:
docker-compose -f ops/docker-compose.yml build api
docker-compose -f ops/docker-compose.yml build worker
```

### 3. Start Stack

Bring up all services:

```bash
docker-compose -f ops/docker-compose.yml up -d
```

Wait 30–60 seconds for services to reach healthy state.

### 4. Verify Health

Check service health:

```bash
docker-compose -f ops/docker-compose.yml ps
```

Expected output:
```
NAME                COMMAND                  SERVICE             STATUS              PORTS
anpr-postgres       "postgres"               postgres            Up (healthy)        0.0.0.0:5432->5432/tcp
anpr-redis          "redis-server ..."       redis               Up (healthy)        0.0.0.0:6379->6379/tcp
anpr-minio          "server /data ..."       minio               Up (healthy)        0.0.0.0:9000->9000/tcp, 0.0.0.0:9001->9001/tcp
anpr-prometheus     "prometheus ..."         prometheus          Up (healthy)        0.0.0.0:9090->9090/tcp
anpr-grafana        "/run.sh"                grafana             Up (healthy)        0.0.0.0:3001->3000/tcp
anpr-api            "uvicorn api.main ..."   api                 Up (healthy)        0.0.0.0:8000->8000/tcp
anpr-worker         "celery -A workers ..."  worker              Up (running)        (internal)
```

### 5. Test API Health

API must respond to `/healthz` with 200:

```bash
curl -v http://localhost:8000/healthz
# Expected: {"status":"ok"}

curl -v http://localhost:8000/readyz
# Expected: {"status":"ready"}
```

### 6. Test Database

Verify PostgreSQL is accessible:

```bash
psql postgresql://anpr:anpr_dev_pw@localhost:5432/anpr -c "SELECT 1;"
# Expected: ?column?
# -----------
#         1
```

### 7. Test Redis

Verify Redis is accessible:

```bash
redis-cli ping
# Expected: PONG
```

### 8. Test Celery Worker

Check worker logs:

```bash
docker-compose -f ops/docker-compose.yml logs worker
# Should show: "worker ready to accept tasks"
```

## Accessing Services

| Service | URL | Credentials |
|---------|-----|-------------|
| FastAPI Docs | http://localhost:8000/docs | (none) |
| FastAPI OpenAPI | http://localhost:8000/openapi.json | (none) |
| Prometheus | http://localhost:9090 | (none) |
| Grafana | http://localhost:3001 | admin / admin |
| MinIO Console | http://localhost:9001 | anpr_admin / anpr_dev_pw |
| PostgreSQL | localhost:5432 | anpr / anpr_dev_pw |
| Redis | localhost:6379 | (none) |

## Common Commands

### View Logs

```bash
# All services
docker-compose -f ops/docker-compose.yml logs -f

# Specific service
docker-compose -f ops/docker-compose.yml logs -f api
docker-compose -f ops/docker-compose.yml logs -f worker
docker-compose -f ops/docker-compose.yml logs -f postgres
```

### Restart Services

```bash
# Restart all
docker-compose -f ops/docker-compose.yml restart

# Restart specific service
docker-compose -f ops/docker-compose.yml restart api
```

### Stop Stack

```bash
docker-compose -f ops/docker-compose.yml down
```

### Clean Up (Remove Volumes)

```bash
# WARNING: Deletes all data
docker-compose -f ops/docker-compose.yml down -v
```

### Rebuild (After Code Changes)

```bash
docker-compose -f ops/docker-compose.yml build --no-cache api
docker-compose -f ops/docker-compose.yml up -d api
```

## Development Workflow

### Local Development (Without Docker)

Install dependencies and run FastAPI locally:

```bash
pip install -e ".[dev]"
export ANPR_ENV=dev
export DATABASE_URL=postgresql+psycopg://anpr:anpr_dev_pw@localhost:5432/anpr
export REDIS_URL=redis://localhost:6379/0
export S3_ENDPOINT_URL=http://localhost:9000

# Start FastAPI (with auto-reload)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# In another terminal, start Celery worker
celery -A workers.tasks worker --loglevel=info
```

### Docker Development (With Volume Mounts)

Code changes auto-reload via volume mounts:

```bash
docker-compose -f ops/docker-compose.yml up -d
# Edit api/main.py → changes visible immediately (due to --reload)
```

## Troubleshooting

### Service Won't Start (Exit Code 1)

Check logs:

```bash
docker-compose -f ops/docker-compose.yml logs api
```

Common issues:
- **"Cannot connect to database"**: Postgres not healthy yet. Wait 30s, then restart.
  ```bash
  docker-compose -f ops/docker-compose.yml restart postgres
  ```
- **"Module not found"**: Dependencies not installed in Dockerfile. Rebuild.
  ```bash
  docker-compose -f ops/docker-compose.yml build --no-cache api
  ```

### Health Check Failing

API health check requires curl. If failing:

```bash
# Check if service is actually running
docker-compose -f ops/docker-compose.yml ps
docker-compose -f ops/docker-compose.yml logs api

# Test manually
curl http://localhost:8000/healthz
```

### Port Already in Use

Ports bound to existing services:

```bash
# Find process using port 8000
lsof -i :8000
# Kill and retry
docker-compose -f ops/docker-compose.yml up -d api
```

### OrbStack Issues

If using OrbStack and services won't start:

1. Switch context:
   ```bash
   docker context use orbstack
   ```

2. Rebuild images:
   ```bash
   docker-compose -f ops/docker-compose.yml build --no-cache
   ```

3. If still failing, fall back to Docker Desktop:
   ```bash
   docker context use desktop-linux
   docker-compose -f ops/docker-compose.yml up -d
   ```

## Gate Criteria (M6 Day 1)

- [x] All 7 services defined in docker-compose.yml
- [x] `docker-compose up` brings all to healthy state
- [x] `curl http://localhost:8000/healthz` returns 200
- [x] `curl http://localhost:5432` → postgres responds
- [x] Celery worker logs show "worker ready to accept tasks"
- [ ] Alembic migrations applied (Day 1 follow-up)
- [ ] JWT login endpoint live (Day 2)
- [ ] All 14 endpoints live (Day 3–4)
- [ ] 100+ tests passing (Days 3–5)

## Files

- `docker-compose.yml` — Service definitions
- `../Dockerfile.api` — FastAPI multi-stage build
- `../Dockerfile.worker` — Celery multi-stage build
- `../api/main.py` — FastAPI app factory
- `../api/config.py` — Pydantic settings (all env vars)
- `../workers/tasks.py` — Celery task queue
- `../.env` — Local secrets (gitignored)
- `../.env.example` — Template with placeholders

## Next Steps (Day 2–5)

- **Day 2**: SQLAlchemy models + Alembic migration 001_init_schema
- **Day 2**: JWT auth system (login, refresh, RBAC)
- **Day 3**: Core endpoints (streams, plates, pagination, search)
- **Day 4**: WebSocket + Watchlist + Celery tasks + rate limiting
- **Day 5**: Audit log + health checks + M6 gate verification
