# Docker & Docker Compose Troubleshooting Guide

## Quick Diagnostics

Run this when things break:

```bash
# 1. Check service health
docker-compose ps

# 2. Check container logs
docker-compose logs --tail=50

# 3. Check specific service
docker-compose logs api --tail=20

# 4. Verify network connectivity
docker-compose exec api ping redis

# 5. Check disk space
docker system df

# 6. Validate compose file
docker-compose config
```

---

## Common Issues & Solutions

### 1. "Ports Already in Use"

**Error Message:**
```
ERROR: for anpr_postgres  Cannot start service postgres: Bind for 0.0.0.0:5432 failed: port is already allocated
```

**Causes:**
- Another service is using the port
- Stale Docker containers

**Solution:**
```bash
# Option A: Stop conflicting service
lsof -i :5432          # Find PID
kill -9 <PID>

# Option B: Stop all docker-compose services
make dev-down

# Option C: Change port in docker-compose.override.yml
# Change "5432:5432" to "5433:5432"
```

---

### 2. "Service Unhealthy"

**Error Message:**
```
ERROR: for anpr_postgres  Service "postgres" failed to start (exit code: 1)
```

**Causes:**
- Database initialization failed
- Volume permissions issue
- Corrupted data in volume

**Solution:**
```bash
# Check logs
docker-compose logs postgres

# Option A: Fix volume permissions
docker-compose down -v  # Remove volumes
docker-compose up -d postgres
docker-compose logs postgres  # Check initialization

# Option B: Reset everything
make docker-nuke
make dev-setup
```

---

### 3. "Connection Refused"

**Error Message:**
```
Error: database connection refused (postgresql)
Error: redis connection refused
```

**Causes:**
- Service not running
- Service not ready (didn't wait)
- Wrong hostname/port

**Diagnosis:**
```bash
# Check if service is running
docker-compose ps

# Status should be "Up" (not "Exit" or "Created")
# If not:
docker-compose up -d --wait
sleep 5

# Check service is listening
docker-compose exec api nc -zv postgres 5432
docker-compose exec api nc -zv redis 6379
```

**Solution:**
```bash
# Wait for services to be healthy
docker-compose up -d --wait

# Or wait manually
docker-compose exec postgres pg_isready -U postgres

# Then test connection
docker-compose exec api python -c "import psycopg; psycopg.connect('postgresql://anpr:anpr_dev_pw@postgres:5432/anpr_db')"
```

---

### 4. "Out of Memory / Disk Space"

**Error Message:**
```
no space left on device
Killed (OOM)
```

**Causes:**
- Docker images taking up space
- Old volumes accumulating
- Large log files

**Solution:**
```bash
# Check disk usage
docker system df

# Clean up unused resources
docker system prune -a --volumes

# Or just this project
make docker-nuke

# Remove old images
docker image prune -a

# Clear logs
docker system prune --volumes
```

---

### 5. "Hot-Reload Not Working"

**Symptoms:**
- Changes to Python files don't reload
- Have to restart container manually

**Causes:**
- Volume not mounted
- uvicorn reload option disabled
- File watcher limit exceeded

**Solution:**
```bash
# Verify volume mount
docker-compose exec api ls -la /app/api/main.py

# If file doesn't exist, volume isn't mounted
# Solution: restart
make docker-restart

# If uvicorn isn't using --reload
# Check docker-compose.override.yml has:
command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# If file watcher limit is exceeded (many files)
ulimit -n 2048  # Increase file descriptor limit
make docker-restart
```

---

### 6. "Permission Denied" in Container

**Error Message:**
```
PermissionError: [Errno 13] Permission denied: '/app/...'
```

**Causes:**
- Container running as root or wrong user
- Volume ownership mismatch

**Solution:**
```bash
# Check who owns files
ls -l api/

# Should match container user (appuser, UID 1000)
# If not, fix permissions
sudo chown -R 1000:1000 .

# Then restart
make docker-restart
```

---

### 7. "Database Initialization Failed"

**Error Message:**
```
FATAL: password authentication failed for user "postgres"
```

**Causes:**
- Wrong environment variables
- Volume has stale data

**Solution:**
```bash
# Check .env.local has correct values
cat .env.local | grep POSTGRES

# Reset database
make docker-nuke
make dev-setup

# Or manually
docker-compose down -v
docker-compose up -d postgres
docker-compose exec postgres psql -U postgres -c "CREATE USER anpr WITH PASSWORD 'anpr_dev_pw';"
```

---

### 8. "Worker Not Processing Tasks"

**Error Message:**
```
Celery worker not picking up tasks
Tasks stuck in Redis queue
```

**Causes:**
- Worker not running
- Broker connection failed
- Task serialization error

**Solution:**
```bash
# Check worker is running
docker-compose ps worker

# Check worker logs
docker-compose logs worker --tail=50

# Verify Redis connection
docker-compose exec worker redis-cli KEYS '*'

# Restart worker
docker-compose restart worker

# Or rebuild
docker-compose build worker
docker-compose up -d worker

# Clear stuck tasks
docker-compose exec redis redis-cli FLUSHDB
```

---

### 9. "MinIO Connection Errors"

**Error Message:**
```
S3 connection error: could not resolve 'minio'
```

**Causes:**
- MinIO service not running
- Network connectivity issue
- Wrong endpoint URL

**Solution:**
```bash
# Check MinIO is running
docker-compose ps minio

# Check logs
docker-compose logs minio

# Verify endpoint URL in .env.local
echo $S3_ENDPOINT_URL
# Should be: http://minio:9000 (not localhost:9000)

# Test connectivity
docker-compose exec api curl -v http://minio:9000

# Restart MinIO
docker-compose restart minio
```

---

### 10. "PostgreSQL Performance Issues"

**Symptoms:**
- Queries are slow
- Database locks
- High CPU/memory usage

**Diagnosis:**
```bash
# Connect to database
make psql

# Check slow queries
SELECT * FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat_statements%'
ORDER BY mean_exec_time DESC LIMIT 5;

# Check active connections
SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;

# Check table sizes
SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

**Solution:**
```bash
# Rebuild indexes
REINDEX DATABASE anpr_db;

# Analyze statistics
ANALYZE;

# Increase pool size if too many connections
# In .env.local:
DB_POOL_SIZE=30  # was 20
DB_MAX_OVERFLOW=60  # was 40

# Restart API
make docker-restart
```

---

### 11. "Network Issues Between Containers"

**Error Message:**
```
Cannot resolve hostname 'postgres'
timeout connecting to redis
```

**Causes:**
- Docker network misconfigured
- Service name typo
- DNS resolution issue

**Solution:**
```bash
# Check Docker network
docker network ls
docker inspect <network-name>

# Test DNS from container
docker-compose exec api nslookup postgres
docker-compose exec api nslookup redis

# If fails, recreate network
docker-compose down
docker-compose up --build

# Or check docker-compose.yml has correct service names
grep -E "^  [a-z]+:" docker-compose.yml
```

---

### 12. "API Can't Reach Frontend (CORS)"

**Error Message:**
```
Access-Control-Allow-Origin header missing
CORS policy: no 'Access-Control-Allow-Origin' header
```

**Causes:**
- CORS origins not configured
- Frontend origin not in whitelist

**Solution:**
```bash
# Check FRONTEND_ORIGINS in .env.local
cat .env.local | grep FRONTEND_ORIGINS

# Should include your frontend URL:
FRONTEND_ORIGINS=http://localhost:3000,http://localhost:5173

# Update if needed
# Restart API
make docker-restart

# Test CORS
curl -X OPTIONS http://localhost:8000/v1/auth/login \
  -H "Origin: http://localhost:3000" \
  -v
```

---

### 13. "Docker Daemon Not Running"

**Error Message:**
```
Cannot connect to Docker daemon
Is the docker daemon running?
```

**Solution (macOS):**
```bash
# Start Docker Desktop
open -a Docker

# Or use OrbStack (faster)
orbstack

# Wait 10 seconds for daemon
sleep 10

# Verify
docker ps
```

---

### 14. "M1/M2 Mac Compatibility Issues"

**Error Message:**
```
exec /usr/local/bin/docker-compose: exec format error
incompatible architecture
```

**Solution:**
```bash
# Use native Docker Desktop (Apple Silicon support added in 4.3)
# Or use OrbStack (fully native)

# Update Docker
brew upgrade docker-desktop
# or
brew install orbstack

# For custom images, ensure they're multi-arch
docker build --platform linux/amd64 -t anpr:latest .
```

---

## Advanced Debugging

### View Docker Logs with Timestamps
```bash
docker-compose logs --timestamps --tail=100
```

### Execute Commands in Running Container
```bash
# Interactive shell
docker-compose exec api bash

# Run Python
docker-compose exec api python -c "import db; print(db.models)"

# Check environment
docker-compose exec api env | grep DATABASE
```

### Inspect Container Resources
```bash
# CPU/memory usage
docker stats

# Network traffic
docker-compose exec api tcpdump -i eth0 -n

# File descriptors
docker-compose exec api lsof
```

### Rebuild Everything from Scratch
```bash
# Option A: Keep data
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Option B: Nuke everything
make docker-nuke
make dev-setup
```

### Check Docker Logs (Daemon Level)
```bash
# macOS
log stream --level debug --predicate 'process == "Docker"'

# Linux
journalctl -u docker -f
```

---

## Performance Tuning

### Docker Desktop Settings (macOS)
1. **Docker Desktop** → **Settings** → **Resources**
   - CPUs: 4–6 cores
   - Memory: 6–8 GB
   - Swap: 2 GB
   - Disk: 64 GB

2. **File Sharing** (if slow I/O)
   - Prefer native volumes over mounted directories
   - Or use VirtioFS (faster than osxfs)

### Docker Compose Optimization
```bash
# Use buildkit (faster builds)
export DOCKER_BUILDKIT=1

# Rebuild (parallel)
docker-compose build --parallel

# Prune unused resources
docker system prune -a
```

---

## Monitoring & Observability

### Real-Time Logs
```bash
# All services
make dev-logs

# Specific service
docker-compose logs -f api --tail=50

# Follow + timestamps
docker-compose logs -f --timestamps api
```

### Health Check Status
```bash
# Show health status
docker-compose ps

# Check individual service
docker-compose exec api curl http://localhost:8000/healthz

# Detailed health info
docker inspect anpr_postgres | grep -A 10 'Health'
```

### Resource Monitoring
```bash
# Real-time stats
docker stats --no-stream

# Continuous monitoring
watch -n 1 'docker stats --no-stream'

# Check specific container
docker stats anpr_postgres --no-stream
```

---

## Recovery Procedures

### Full Environment Reset
```bash
# Stop and remove everything
make docker-nuke

# Reinstall from scratch
make dev-setup

# Verify
make test
```

### Partial Recovery (Keep Some Data)
```bash
# Keep database, reset cache
docker-compose restart postgres

# Keep everything, just restart API
docker-compose restart api

# Rebuild just API image
docker-compose build api
docker-compose up -d api
```

### Data Backup Before Dangerous Operations
```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U anpr anpr_db > backup.sql

# Backup Redis
docker-compose exec redis redis-cli BGSAVE
docker cp anpr_redis:/data/dump.rdb ./redis_backup.rdb

# Restore if needed
docker-compose exec postgres psql -U anpr anpr_db < backup.sql
```

---

## When All Else Fails

```bash
# Nuclear option: reset everything
make clean
make docker-nuke
rm -rf .env.local

# Start fresh
make dev-setup

# Verify
make test
```

If still broken:
1. Check GitHub Issues for similar problems
2. Review Docker logs: `docker system events --follow`
3. Check disk/memory: `docker system df`, `docker stats`
4. Post to #dev-help with: `docker-compose ps`, `docker-compose logs`, `.env.local` (sanitized)
