# Local Development Environment Setup

This guide walks you through setting up a complete ANPR development environment that mirrors production.

## Quick Start (5 minutes)

### 1. First-Time Setup
```bash
# Clone the repo (if not already done)
git clone <repo-url>
cd ComputerVision\ Project

# One-command setup: installs deps, generates secrets, starts services
make dev-setup
```

This does everything:
- Installs Python dependencies via `uv`
- Generates encryption keys
- Starts docker-compose stack (postgres, redis, minio, api, worker)
- Runs database migrations
- Seeds test data

**Result:** Your local environment is ready. You should see:
```
✓ Development environment ready!

Available endpoints:
  API:             http://localhost:8000
  API Docs:        http://localhost:8000/docs
  pgAdmin:         http://localhost:5050
  Redis Commander: http://localhost:8081
  MinIO Console:   http://localhost:9001

Test user credentials:
  Email:    test@example.com
  Password: password123
```

### 2. Verify Everything Works
```bash
# Run the test suite (unit + integration)
make test

# Expected: All tests pass (40+ tests)
```

### 3. Start Developing
```bash
# View API docs in browser
open http://localhost:8000/docs

# Follow logs as you code
make dev-logs

# Edit code in your IDE → changes auto-reload in the container
```

---

## Environment Details

### Stack Components

| Service | Port | Purpose | Access |
|---------|------|---------|--------|
| **PostgreSQL 16** | 5432 | Primary database | `localhost:5432` |
| **Redis 7** | 6379 | Cache, task broker | `localhost:6379` |
| **MinIO** | 9000/9001 | S3-compatible object storage | Console: `http://localhost:9001` |
| **FastAPI** | 8000 | ANPR API | `http://localhost:8000` |
| **Celery** | N/A | Background task worker | Async tasks |
| **pgAdmin** | 5050 | PostgreSQL UI | `http://localhost:5050` |
| **Redis Commander** | 8081 | Redis UI | `http://localhost:8081` |

### Configuration Files

- **`.env.local`** — Local secrets and environment variables (git-ignored, never commit)
  - Auto-generated on `make dev-setup`
  - Override settings here for local testing

- **`docker-compose.yml`** — Production-like base configuration
  - Postgres 16, Redis 7 (same as prod)
  - Volume mounts for persistent data

- **`docker-compose.override.yml`** — Local development overrides
  - Hot-reload for API and worker
  - Additional dev tools (pgAdmin, Redis Commander)
  - Auto-loaded by `docker compose` (no need to specify)

- **`pyproject.toml`** — Python dependencies and project config
- **`Makefile.dev`** — Quick-access development commands

---

## Daily Development Workflow

### Start of Day
```bash
# Start all services (if not already running)
make dev-up

# Initialize database (runs migrations + seeds test data)
make dev-init

# Follow logs
make dev-logs &
```

### During Development

#### Edit Code + Hot-Reload
```bash
# Edit your Python files in your IDE
# Changes auto-reload in the container (no rebuild needed!)
# Exception: changes to dependencies (pyproject.toml) require `docker-compose restart`
```

#### Run Tests
```bash
# All tests
make test

# Unit tests only
make test-unit

# Integration tests (requires docker-compose running)
make test-int

# Watch mode (reruns tests on file changes)
make test-watch

# With coverage
make test-cov
```

#### Database Inspection
```bash
# PostgreSQL CLI
make psql

# Redis CLI
make redis-cli

# pgAdmin UI (point-and-click)
open http://localhost:5050
# Login: dev@example.com / devpassword
```

#### Code Quality
```bash
# Format code
make fmt

# Check formatting + linting
make lint

# Both
make fmt && make lint
```

#### API Documentation
```bash
# View interactive API docs
open http://localhost:8000/docs

# Or curl individual endpoints
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'
```

#### Follow Logs
```bash
# All services
make dev-logs

# API only
make dev-logs-api

# Worker only
make dev-logs-worker
```

### End of Day
```bash
# Stop services (keeps data)
make dev-down

# Or remove containers entirely (still keeps volumes)
make docker-clean
```

---

## Common Tasks

### Reset Database (Destructive)
```bash
# Drops all tables and recreates from scratch
make dev-reset

# Or just reseed with fresh test data
make db-seed
```

### Inspect Database Schema
```bash
# Using pgAdmin
open http://localhost:5050

# Or using CLI
make psql
# Then: \dt (list tables), \d <table> (describe table)
```

### Check Redis Cache
```bash
# Using Redis Commander
open http://localhost:8081

# Or using CLI
make redis-cli
# Then: KEYS * (list keys), GET <key> (get value)
```

### Test Celery Task Execution
```bash
# View worker logs
make dev-logs-worker

# Or run a test that triggers tasks
make test-int -k celery
```

### Generate New Encryption Keys
```bash
# If you need to regenerate secrets
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Update .env.local with new values
# Restart services: make docker-restart
```

### View MinIO Console
```bash
# MinIO admin console for file uploads/downloads
open http://localhost:9001
# Credentials: minioadmin / minioadmin

# Access from API (S3-compatible):
# s3://anpr-crops/  (plate crops)
# s3://anpr-frames/ (original frames)
# s3://anpr-audit/  (audit logs)
```

---

## Troubleshooting

### Problem: `docker-compose: command not found`
**Solution:** Install Docker Desktop or Docker via Homebrew
```bash
# macOS
brew install docker

# Or use OrbStack (faster, more efficient)
brew install orbstack
```

### Problem: `Postgres connection refused`
**Solution:** Check if services are running
```bash
# Start services
make dev-up

# Check health
make health

# View logs
make dev-logs
```

### Problem: Port Already in Use
**Error:** `bind: address already in use`

**Solution:** Find and stop conflicting services
```bash
# Find what's using port 5432 (Postgres)
lsof -i :5432
kill -9 <PID>

# Or just use docker-compose down
make dev-down

# Then restart
make dev-up
```

### Problem: Tests Fail with "Database connection refused"
**Solution:** Ensure docker-compose is running
```bash
# Start services
make dev-up

# Initialize database
make dev-init

# Run tests
make test
```

### Problem: Hot-Reload Not Working
**Solution:** Check if file is mounted correctly
```bash
# Verify volume mount
docker-compose ps
docker-compose exec api ls -la /app

# If not mounted, restart
make docker-restart
```

**Note:** Changes to `pyproject.toml` require a full restart:
```bash
make docker-restart
```

### Problem: Tests Pass Locally but Fail in CI
**Solution:** Ensure you're testing against the actual containers
```bash
# Don't skip docker-compose
make test-int

# Check that your changes are committed
git status
```

### Problem: Database Migrations Conflict
**Solution:** Reset to clean state
```bash
# Drop all tables and reseed
make dev-reset

# Or manually handle it
make psql
# DELETE FROM alembic_version;
# DROP TABLE IF EXISTS <table_name> CASCADE;
make db-migrate
```

### Problem: Out of Disk Space
**Solution:** Clean up Docker resources
```bash
# Remove unused images/volumes (careful!)
docker system prune -a

# Or just clean up this project
make docker-nuke

# Then restart
make dev-setup
```

### Problem: Worker Not Processing Tasks
**Solution:** Check worker logs and Redis connection
```bash
# View worker logs
make dev-logs-worker

# Check Redis
make redis-cli
# KEYS *  (should show pending tasks)

# Restart worker
make docker-restart
```

### Problem: `.env.local` Not Loading
**Solution:** Ensure file exists and is properly formatted
```bash
# Check file exists
ls -la .env.local

# Verify it's valid (no syntax errors)
make health
```

---

## Environment Variables

### Required (Auto-Generated by `make dev-setup`)
- `JWT_SECRET` — JWT token signing key (min 32 chars)
- `CELERY_ENCRYPTION_KEY` — Celery task encryption (44 chars, base64)
- `FERNET_KEY` — Fernet symmetric encryption (44 chars, base64)

### Auto-Set by docker-compose
- `DATABASE_URL=postgresql+asyncpg://anpr:anpr_dev_pw@postgres:5432/anpr_db`
- `REDIS_URL=redis://redis:6379/0`
- `S3_ENDPOINT_URL=http://minio:9000`

### Override for Testing
Edit `.env.local`:
```bash
# Change log level
LOG_LEVEL=DEBUG

# Disable HTTPS redirect in dev
ANPR_ENV=dev

# Add your test data credentials
POSTGRES_PASSWORD=custom_password
```

---

## IDE Integration

### VS Code
```bash
# Python: Select interpreter
# Command Palette > Python: Select Interpreter
# Choose .venv in the repo root

# Optional: Install extensions
# - Python (ms-python.python)
# - Pylance (ms-python.vscode-pylance)
# - Docker (ms-vscode.docker)

# Debugging: Add to .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Current File",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "justMyCode": true
    },
    {
      "name": "Python: pytest",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["${file}"],
      "justMyCode": true
    }
  ]
}
```

### PyCharm
1. **File** → **Settings** → **Project** → **Python Interpreter**
2. Click ⚙️ → **Add**
3. Select "Existing Environment"
4. Choose `.venv/bin/python`
5. **Apply** → **OK**

For debugging:
- Set breakpoints with `pdb` or PyCharm's built-in debugger
- Run → **Debug** (or press `Ctrl+D` on macOS)

### Docker Debugging
Attach debugger to running container:
```bash
# Edit Makefile.dev, uncomment stdin_open/tty for api service
docker-compose exec -it anpr_api python

# Or use pdb in container
make dev-logs-api
# (your breakpoint will appear in logs)
```

---

## Performance Tips

### Reduce Build Time
- Docker images are cached. To skip rebuilds: `make dev-up` (no `--build`)
- If dependencies change: `make docker-restart`

### Faster Tests
```bash
# Skip slow tests
make test -k "not slow"

# Parallel execution
make test-unit -- -n auto

# Watch mode for TDD
make test-watch
```

### Database Performance
```bash
# Indexes are automatically created via Alembic
# Check with:
make psql
# \d <table_name>  (shows indexes)

# Connection pooling is configured in config.py
# Adjust pool size if needed:
# DB_POOL_SIZE=20 (default)
```

---

## Cleanup & Reset

### Keep Data, Stop Services
```bash
make dev-down
```

### Remove Containers, Keep Data
```bash
make docker-clean
```

### Full Reset (Delete Everything)
```bash
make docker-nuke
make dev-setup  # Rebuild from scratch
```

---

## Next Steps

1. **Read the API Docs:** `open http://localhost:8000/docs`
2. **Run Tests:** `make test` (verify setup)
3. **Start Coding:** Edit files in `api/`, `workers/`, `db/` → auto-reload
4. **Commit & Push:** `git add . && git commit -m "feature: ..."`

---

## Reference: All Make Commands

```bash
make help          # Show all available commands

# Setup & Infrastructure
make dev-setup     # [First time] Install + start everything
make dev-up        # Start docker-compose services
make dev-down      # Stop services (keep data)
make dev-init      # Run migrations + seed database
make dev-reset     # [Destructive] Drop all tables, recreate

# Database
make db-migrate    # Run Alembic migrations
make db-seed       # Seed test data
make psql          # PostgreSQL CLI
make redis-cli     # Redis CLI

# Testing
make test          # Run all tests
make test-unit     # Unit tests only
make test-int      # Integration tests only
make test-watch    # Watch mode (reruns on changes)
make test-cov      # With coverage report

# Code Quality
make fmt           # Format code with ruff
make lint          # Lint + type check
make fmt-check     # Check formatting (no changes)

# Utilities
make dev-logs      # Follow all service logs
make docker-ps     # Show running containers
make docker-clean  # Remove containers (keep data)
make clean         # Remove Python caches
```

---

## Support

**Issues?** Check the **Troubleshooting** section above.

**Questions?** Review `api/main.py` for app startup, `db/models.py` for schema, `tests/conftest.py` for test setup.

**Contributing?** Follow the code style in `.ruff.toml` and `pyproject.toml`.
