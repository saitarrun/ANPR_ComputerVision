# ANPR Backend Docker Guide

Comprehensive guide to building, running, and deploying the ANPR FastAPI backend using Docker and Docker Compose.

## Quick Start (Local Development)

### Prerequisites
- Docker Desktop (or OrbStack on macOS)
- Docker Compose 2.0+

### Setup

1. **Copy environment template**
   ```bash
   cp .env.example .env.local
   # Edit .env.local with your secrets
   ```

2. **Start the stack**
   ```bash
   docker-compose up -d
   ```

   This launches:
   - **API** (FastAPI): http://localhost:8000
   - **Docs** (Swagger UI): http://localhost:8000/docs
   - **PostgreSQL**: localhost:5432
   - **Redis**: localhost:6379
   - **Celery Worker**: async task processing
   - **MinIO** (S3-compatible): http://localhost:9001

3. **Initialize database** (first time only)
   ```bash
   docker-compose exec api alembic upgrade head
   ```

4. **Run migrations**
   ```bash
   docker-compose exec api alembic upgrade head
   docker-compose exec api python -m scripts.seed_db
   ```

5. **Verify health**
   ```bash
   curl http://localhost:8000/healthz
   curl http://localhost:8000/readyz
   ```

### Development Workflow

**Code hot-reload** — modify files in `api/`, `workers/`, `db/`, `anpr_core/` and changes reflect instantly in running containers. Volumes are mounted:

```yaml
volumes:
  - ./api:/app/api
  - ./workers:/app/workers
  - ./db:/app/db
  - ./anpr_core:/app/anpr_core
```

**View logs**
```bash
docker-compose logs -f api
docker-compose logs -f celery-worker
docker-compose logs -f postgres
```

**Restart services**
```bash
docker-compose restart api celery-worker
```

**Stop everything**
```bash
docker-compose down
docker-compose down -v  # Also remove persistent volumes
```

---

## Building Docker Images

### Local Build

```bash
docker build -t anpr-backend:dev -f Dockerfile .
```

### CI/CD Build Script

Use the provided shell script for reproducible, artifact-tracked builds:

```bash
./scripts/docker-build.sh [OPTIONS]
```

**Options:**
- `--registry REGISTRY` — Docker registry (default: `docker.io`)
- `--image IMAGE` — Image name (default: `anpr-backend`)
- `--tag TAG` — Image tag (default: git commit hash)
- `--push` — Push to registry after build
- `--no-cache` — Skip Docker layer cache
- `--dry-run` — Show commands without executing

**Examples:**

```bash
# Build with commit hash tag
./scripts/docker-build.sh

# Build and push to ECR
./scripts/docker-build.sh \
  --registry 123456789.dkr.ecr.us-east-1.amazonaws.com \
  --image anpr-backend \
  --tag v0.1.0 \
  --push

# Build without cache
./scripts/docker-build.sh --no-cache

# Dry-run
./scripts/docker-build.sh --dry-run
```

### Image Tagging Strategy

Images are tagged with:
- **Git commit hash** (short): `anpr-backend:abc1234`
- **Semantic version**: `anpr-backend:v0.1.0` (releases only)
- **`latest`**: Always points to the most recent build

**Tagging ensures:**
- Reproducible deployments (image content tied to exact commit)
- Quick rollbacks (revert to previous commit hash)
- Audit trail (know what code is in production)

---

## Production Deployment

### Multi-Stage Build (Production Optimization)

The `Dockerfile` uses multi-stage builds:

1. **Stage 1 (Builder)**: Compiles dependencies, builds venv (discarded after)
2. **Stage 2 (Runtime)**: Minimal image with only runtime deps, venv from builder

**Benefits:**
- Final image ~30% smaller than single-stage
- No build tools in production (reduced attack surface)
- Faster pulls and deployments

### Docker Compose for Production

Use production overrides:

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Production changes:**
- Resource limits (CPU, memory)
- Stricter health checks
- Enhanced restart policies
- Optimized database config
- MinIO removed (use AWS S3 instead)

### Environment Variables

**Secrets management** (never commit secrets to git):

1. **AWS Secrets Manager** (recommended for AWS)
   ```bash
   aws secretsmanager get-secret-value --secret-id anpr/prod/env \
     | jq -r '.SecretString' > /tmp/prod.env
   docker-compose --env-file /tmp/prod.env up
   ```

2. **HashiCorp Vault**
   ```bash
   vault kv get -format=env secret/anpr/prod > /tmp/prod.env
   docker-compose --env-file /tmp/prod.env up
   ```

3. **.env file** (development only; use secrets manager for prod)
   ```bash
   docker-compose --env-file .env.prod up
   ```

**Required secrets:**
- `JWT_SECRET` (32+ chars, random)
- `CELERY_ENCRYPTION_KEY` (44+ chars, Fernet-compatible)
- `FERNET_KEY` (44+ chars, Fernet-compatible)
- `POSTGRES_PASSWORD` (strong, 16+ chars)
- `S3_ACCESS_KEY`, `S3_SECRET_KEY` (if using S3)

---

## Kubernetes Deployment (Optional)

For production at scale, build Kubernetes manifests from docker-compose:

```bash
kompose convert -f docker-compose.yml -o k8s/
```

Or use Helm charts (see `k8s/helm/` if available).

---

## Health Checks & Readiness Probes

The API exposes two health endpoints:

### Liveness (`/healthz`)
- Lightweight, always succeeds (if container is alive)
- **Used by**: Container restart policies
- **Response**: `{"status": "ok"}`

### Readiness (`/readyz`)
- Checks database connectivity
- **Used by**: Load balancers, Kubernetes readiness probes
- **Response**: `{"status": "ready"}` or HTTP 503

**In docker-compose:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/readyz"]
  interval: 30s
  timeout: 10s
  retries: 3
```

**In Kubernetes:**
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /readyz
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## Database Migrations (Alembic)

Migrations run at container startup via the `lifespan` context manager in `api/main.py`.

**Manual migration:**
```bash
docker-compose exec api alembic upgrade head
```

**Create new migration:**
```bash
docker-compose exec api alembic revision --autogenerate -m "Add column X"
docker-compose exec api alembic upgrade head
```

---

## Logging & Observability

### Structured Logging

All logs are structured JSON, logged to stdout:
```json
{
  "timestamp": "2026-05-28T10:30:00Z",
  "level": "INFO",
  "service": "anpr-api",
  "request_id": "abc-123",
  "message": "Request completed",
  "status": 200,
  "duration_ms": 45
}
```

**Capture logs:**
```bash
docker-compose logs -f api | jq '.level'  # Filter by field
```

### Log Aggregation

For production, forward logs to CloudWatch, ELK, or Splunk:

```bash
docker-compose logs -f api | \
  aws logs put-log-events \
  --log-group-name /anpr/prod/api \
  --log-stream-name api-001
```

---

## Troubleshooting

### Container won't start

```bash
docker-compose logs api
# Check: Database URL, secrets, migrations
```

### Database connection timeout

```bash
# Verify postgres is healthy
docker-compose ps postgres
# Check logs
docker-compose logs postgres
# Restart postgres
docker-compose restart postgres
```

### Celery worker not picking up tasks

```bash
docker-compose logs celery-worker
# Check: CELERY_BROKER_URL, Redis connectivity
docker-compose exec redis redis-cli PING
```

### Out of disk space

```bash
# Remove unused images/containers
docker system prune -a
# Remove volumes (warning: deletes data)
docker volume prune
```

---

## Security Best Practices

1. **Non-root user**: Dockerfile runs as `appuser` (UID 1000), not `root`
2. **Minimal base image**: `python:3.11-slim` (no build tools, ~160 MB)
3. **Health checks**: Prevent unhealthy containers from receiving traffic
4. **Secrets in env**: Never hardcode secrets; use secrets manager
5. **Network isolation**: Docker Compose creates isolated network; services communicate by name, not IP
6. **Resource limits**: Set CPU/memory limits to prevent runaway containers

---

## Useful Commands

```bash
# Spin up stack
docker-compose up -d

# View running containers
docker-compose ps

# Execute command in container
docker-compose exec api python -c "..."

# View logs
docker-compose logs -f api

# Rebuild images
docker-compose build --no-cache

# Stop stack
docker-compose stop

# Remove stack (keep volumes)
docker-compose down

# Remove stack + volumes
docker-compose down -v

# Push to registry
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/anpr-backend:v0.1.0
```

---

## Next Steps

1. **Local development**: `docker-compose up -d` → `docker-compose logs -f api`
2. **Test CI/CD**: Push to feature branch → observe build in GitHub Actions
3. **Staging deploy**: Merge to `main` → observe `docker-compose.prod.yml` deployment
4. **Production**: Tag release → ECR push → ECS/EKS rollout

See [DEPLOYMENT.md](DEPLOYMENT.md) for infrastructure-as-code and rollout strategies.
