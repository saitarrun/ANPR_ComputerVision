# ANPR Backend Containerization Design

Complete containerization strategy for the ANPR FastAPI backend, enabling reproducible local development and production deployments.

## Architecture Overview

The solution provides:

1. **Dockerfile** — Multi-stage build for production-grade images
2. **docker-compose.yml** — Full local development stack (API + DB + Cache + Workers)
3. **docker-compose.prod.yml** — Production overrides (resource limits, health checks, security)
4. **.dockerignore** — Optimized build context to reduce image size
5. **scripts/docker-build.sh** — CI/CD build automation with artifact tagging
6. **.github/workflows/docker-build.yml** — GitHub Actions build & push pipeline
7. **Makefile** — Developer convenience commands for common tasks
8. **.env.local** — Local secrets template (never commit to git)
9. **DOCKER.md** — Comprehensive user guide for developers

---

## Design Principles

### 1. Multi-Stage Builds (Optimization)

**Stage 1 (Builder):** Compiles dependencies in full environment
- Installs build tools (gcc, make, etc.)
- Builds Python venv with all dependencies
- Creates optimized wheels

**Stage 2 (Runtime):** Minimal production image
- Only includes runtime dependencies (libpq, curl)
- Copies pre-built venv from builder
- No build tools (reduces attack surface, 30% smaller image)

**Result:** ~360MB final image (vs ~520MB single-stage)

### 2. Security by Default

- **Non-root user** (`appuser`, UID 1000) — mitigates container escape attacks
- **Minimal base image** (`python:3.11-slim`, 160MB) — fewer vulnerabilities
- **No hardcoded secrets** — all secrets injected via environment variables
- **Health checks** — prevent unhealthy containers from receiving traffic
- **Network isolation** — Docker Compose creates internal network; services communicate by name

### 3. Developer Experience

- **Code hot-reload** — volumes mount source directories; changes reflect instantly
- **Convenience commands** — `make docker-up`, `make test`, `make db-migrate`
- **Integrated stack** — one command (`docker-compose up -d`) launches everything
- **Clear documentation** — DOCKER.md guides developers through every operation

### 4. Reproducible Deployments

- **Image tagging by commit hash** — every deployment tied to exact source code
- **Semver tagging** — releases tagged `v0.1.0`, `v0.2.0` for easy identification
- **Latest tag** — always points to most recent successful build
- **Artifact attestation** — GitHub Actions records build metadata (who, when, digest)

---

## Directory Structure

```
.
├── Dockerfile                           # Multi-stage build
├── .dockerignore                        # Exclude unnecessary files from build context
├── docker-compose.yml                   # Development stack (API, DB, Redis, Workers, MinIO)
├── docker-compose.prod.yml              # Production overrides (resource limits, health checks)
├── .env.example                         # Environment variable template (version-controlled)
├── .env.local                           # Local overrides (NEVER commit; .gitignore enforced)
├── Makefile                             # Developer convenience commands
├── DOCKER.md                            # Comprehensive Docker guide
├── scripts/
│   └── docker-build.sh                  # CI/CD build script (artifact tagging)
├── .github/workflows/
│   └── docker-build.yml                 # GitHub Actions build & push pipeline
├── api/                                 # FastAPI application
├── workers/                             # Celery workers for async tasks
├── db/                                  # Database models & migrations (Alembic)
├── anpr_core/                           # Core ANPR logic (ML models, detection)
├── ingest/                              # Data ingestion pipeline
└── pyproject.toml                       # Python dependencies (uv/pip)
```

---

## Quick Start

### 1. Local Development (3 commands)

```bash
# Setup (one-time)
make setup

# Start stack
make docker-up

# View logs
make docker-logs-api
```

### 2. Key Operations

```bash
# Run tests
make test

# Database migrations
make db-migrate

# Seed test data
make db-seed

# Open shell in container
make docker-shell

# Stop everything
make docker-down
```

---

## Production Deployment

### Build & Push to Registry

```bash
# Build with commit hash tag (default)
./scripts/docker-build.sh

# Build and push to ECR
./scripts/docker-build.sh \
  --registry 123456789.dkr.ecr.us-east-1.amazonaws.com \
  --image anpr-backend \
  --tag v0.1.0 \
  --push

# Verify image
docker inspect 123456789.dkr.ecr.us-east-1.amazonaws.com/anpr-backend:v0.1.0
```

### Deploy with Production Overrides

```bash
# Use production config (resource limits, health checks)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# OR with environment file from secrets manager
aws secretsmanager get-secret-value --secret-id anpr/prod/env \
  | jq -r '.SecretString' > /tmp/prod.env
docker-compose --env-file /tmp/prod.env up -d
```

### Resource Limits (docker-compose.prod.yml)

| Component | CPU Limit | Memory Limit | Reserve |
|-----------|-----------|--------------|---------|
| API | 2.0 | 2GB | 1.0 / 1GB |
| Celery Worker | 2.0 | 2GB | 1.0 / 1GB |
| PostgreSQL | 2.0 | 4GB | 1.0 / 2GB |
| Redis | 1.0 | 1GB | 0.5 / 512MB |

---

## Environment Variables

### Required (No Defaults)

```bash
JWT_SECRET              # ≥32 chars; generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
CELERY_ENCRYPTION_KEY   # ≥44 chars Fernet-compatible; generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DATABASE_URL            # e.g., postgresql+asyncpg://user:pass@postgres:5432/anpr
REDIS_URL               # e.g., redis://redis:6379/0
S3_*                    # S3 credentials (if using S3; MinIO defaults in docker-compose.yml)
```

### Optional (Have Defaults)

```bash
ANPR_ENV=dev                       # dev | staging | production
LOG_LEVEL=INFO                     # DEBUG | INFO | WARNING | ERROR
API_HOST=0.0.0.0                  # Listen on all interfaces (Docker) or 127.0.0.1 (local)
API_PORT=8000
FRONTEND_ORIGINS=...               # CORS allowed origins (comma-separated)
```

---

## Health Checks

### Liveness Probe (`/healthz`)

- **Purpose:** Container alive check
- **Endpoint:** GET /healthz
- **Response:** `{"status": "ok"}` (always succeeds if container running)
- **Used by:** Docker restart policies, Kubernetes liveness probe

```bash
curl http://localhost:8000/healthz
```

### Readiness Probe (`/readyz`)

- **Purpose:** Service ready to receive traffic
- **Endpoint:** GET /readyz
- **Response:** `{"status": "ready"}` or HTTP 503
- **Checks:** Database connectivity
- **Used by:** Load balancers, Kubernetes readiness probe, health-check.interval

```bash
curl http://localhost:8000/readyz
```

**docker-compose.yml:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/readyz"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

---

## Image Tagging Strategy

### Development

```bash
# Local image (no registry)
docker build -t anpr-backend:dev .

# Run locally
docker run -p 8000:8000 anpr-backend:dev
```

### CI/CD (Feature Branch)

```bash
# Commit hash (short): abc1234
docker build -t ghcr.io/yourorg/anpr-backend:abc1234 .
docker push ghcr.io/yourorg/anpr-backend:abc1234

# Also tag as latest
docker build -t ghcr.io/yourorg/anpr-backend:latest .
docker push ghcr.io/yourorg/anpr-backend:latest
```

### Releases (Tags)

```bash
# Version tag: v0.1.0
docker build -t ghcr.io/yourorg/anpr-backend:v0.1.0 .
docker push ghcr.io/yourorg/anpr-backend:v0.1.0

# Also update latest
docker tag ghcr.io/yourorg/anpr-backend:v0.1.0 ghcr.io/yourorg/anpr-backend:latest
docker push ghcr.io/yourorg/anpr-backend:latest
```

### Tagging Benefits

- **Reproducibility:** Every image tied to exact commit (revert = pull old image)
- **Audit trail:** Know what code is in production
- **Quick rollback:** `docker pull` old commit hash image
- **Release management:** Semantic versions for production releases

---

## CI/CD Pipeline (.github/workflows/docker-build.yml)

Automated build & push on every commit to `main`, `develop`, or version tags:

### Stages

1. **Build** — Compile image with BuildKit cache
2. **Push** — Push to GitHub Container Registry (ghcr.io)
3. **Scan** — Trivy vulnerability scan (blocks on CRITICAL findings)
4. **Attest** — Record build metadata (who, when, digest)

### Triggers

- Push to `main` → Build + push `latest`, `main-abc1234`
- Push to `develop` → Build + push `develop`, `develop-abc1234`
- Tag `v*` (e.g., `v0.1.0`) → Build + push `v0.1.0`, `latest`

### Outputs

- Image reference: `ghcr.io/yourorg/anpr-backend:abc1234`
- Vulnerability scan results: GitHub Security → Vulnerabilities
- Build metadata: GitHub Container Registry → Package details

---

## Troubleshooting

### Build Fails: "pip install -e . fails"

**Cause:** Missing `README.md` (required by pyproject.toml)

**Solution:**
```bash
# Ensure README.md exists and is not in .dockerignore
ls README.md
grep -v "^README.md" .dockerignore > .dockerignore.tmp
mv .dockerignore.tmp .dockerignore
```

### Container Won't Start: "Database connection refused"

**Cause:** PostgreSQL not ready or incorrect DATABASE_URL

**Solution:**
```bash
# Check postgres is running and healthy
docker-compose ps postgres

# View postgres logs
docker-compose logs postgres

# Restart postgres
docker-compose restart postgres

# Verify connection
docker-compose exec postgres psql -U anpr -d anpr -c "SELECT 1"
```

### Out of Disk Space

**Solution:**
```bash
# Remove stopped containers
docker container prune -f

# Remove dangling images
docker image prune -f

# Remove unused volumes (WARNING: deletes data)
docker volume prune -f

# Full cleanup (aggressive)
docker system prune -a --volumes -f
```

---

## Security Checklist

- [ ] Non-root user in Dockerfile (appuser)
- [ ] Resource limits set (docker-compose.prod.yml)
- [ ] Health checks configured (/healthz, /readyz)
- [ ] Secrets in environment variables (not hardcoded)
- [ ] .dockerignore excludes secrets (.env, .aws, etc.)
- [ ] Network isolation (Docker Compose internal network)
- [ ] Vulnerability scans automated (CI/CD pipeline)
- [ ] Image signed (Cosign; optional for GitHub)
- [ ] Image registry is private (ECR, GitHub Container Registry with private access)
- [ ] Logs structured JSON (audit trail)

---

## Next Steps

1. **Local development:**
   ```bash
   make setup          # One-time setup
   make docker-up      # Start stack
   make docker-logs    # Follow logs
   ```

2. **Test CI/CD:**
   - Push to feature branch
   - Observe GitHub Actions build
   - Check image in GitHub Container Registry

3. **Production deployment:**
   - Merge to `main` or tag `v*`
   - GitHub Actions builds and pushes image
   - Deploy using ECS, EKS, or Kubernetes
   - Monitor at `/readyz` endpoint

4. **Observability:**
   - Logs → CloudWatch / ELK (implement log forwarding)
   - Metrics → Prometheus / CloudWatch (add Prometheus exporter)
   - Traces → Jaeger / OpenTelemetry (add tracing instrumentation)

See [DOCKER.md](DOCKER.md) for detailed operational guide.
